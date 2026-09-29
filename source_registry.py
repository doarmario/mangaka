"""Declarative source packages shared by the application and Docker installer.

Standard-library only: reading a package never imports or executes plugin code.
"""
from dataclasses import dataclass
from pathlib import Path
import json
import re
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Source:
    id: str
    name: str
    api_url: str = ''
    config_key: str = ''
    adapter: str = 'manga-api-v1'
    enabled: bool = True
    visible: bool = True
    tags: bool = False
    search: str = 'endpoint'
    pagination: str = 'basic'
    chapter_languages: tuple = ('en',)
    chapter_pagination: bool = False
    image: str = ''
    port: int = 0
    package: str = ''

    def endpoint(self, config):
        if not self.enabled:
            return ''
        return str(config.get(self.config_key, '') if self.config_key else self.api_url).rstrip('/')


BUILTINS = (
    Source('mangadex', 'MangaDex', adapter='mangadex', tags=True),
    Source('asura', 'AsuraScans', config_key='MANGA_NOVEL_API_URL', tags=True, search='complete'),
    Source('qiscans', 'Qi Scans', config_key='QISCANS_API_URL', tags=True, pagination='strict'),
    Source('demonicscans', 'Demonic Scans', config_key='DEMONICSCANS_API_URL', tags=True, search='catalog'),
    Source('thunderscans', 'Thunder Scans', config_key='THUNDERSCANS_API_URL', tags=True, search='catalog'),
    Source('comick', 'ComicK', config_key='MANGA_NOVEL_API_URL', visible=False,
           chapter_languages=('pt-br', 'pt', 'en'), chapter_pagination=True),
    Source('weebcentral', 'WeebCentral', config_key='MANGA_NOVEL_API_URL', visible=False),
)


def read_package(path):
    path = Path(path)
    if path.stat().st_size > 65536:
        raise ValueError('Manifest exceeds 64 KiB')
    raw = json.loads(path.read_text(encoding='utf-8'))
    allowed = {'schema_version', 'id', 'name', 'api_url', 'enabled', 'tags', 'search',
               'pagination', 'chapter_languages', 'chapter_pagination', 'service'}
    if not isinstance(raw, dict) or set(raw) - allowed:
        raise ValueError('Unknown manifest fields')
    if type(raw.get('schema_version')) is not int or raw['schema_version'] != 1:
        raise ValueError('Unsupported schema_version; expected 1')
    identifier = raw.get('id')
    if not isinstance(identifier, str) or not re.fullmatch(r'[a-z][a-z0-9_-]{0,31}', identifier):
        raise ValueError('Invalid source ID')
    if identifier != path.parent.name:
        raise ValueError('Source ID must match its package directory')
    if identifier in {s.id for s in BUILTINS}:
        raise ValueError('Package ID conflicts with a built-in source')
    name = raw.get('name')
    if not isinstance(name, str) or not name.strip() or len(name) > 80:
        raise ValueError('A source name of 1–80 characters is required')
    for field in ('enabled', 'tags', 'chapter_pagination'):
        if field in raw and type(raw[field]) is not bool:
            raise ValueError(f'{field} must be a boolean')
    search, pagination = raw.get('search', 'endpoint'), raw.get('pagination', 'basic')
    if search not in ('endpoint', 'catalog', 'complete') or pagination not in ('basic', 'strict'):
        raise ValueError('Unsupported search or pagination mode')
    languages = raw.get('chapter_languages', ['en'])
    if (not isinstance(languages, list) or not languages or
            any(lang not in ('pt-br', 'pt', 'en') for lang in languages)):
        raise ValueError('chapter_languages must contain pt-br, pt, or en')
    image, port, endpoint = '', 0, raw.get('api_url', '')
    service = raw.get('service')
    if service is not None:
        if not isinstance(service, dict) or set(service) != {'image', 'port'} or endpoint:
            raise ValueError('Use api_url OR service with image and port')
        image, port = service['image'], service['port']
        if (not isinstance(image, str) or len(image) > 255 or
                not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._/:@-]*', image)):
            raise ValueError('Invalid Docker image reference')
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError('Service port must be between 1 and 65535')
        endpoint = f'http://source-{identifier}:{port}'
    if not isinstance(endpoint, str):
        raise ValueError('api_url must be a string')
    try:
        parsed = urlsplit(endpoint)
        valid = (parsed.scheme in ('http', 'https') and parsed.hostname and
                 not parsed.username and not parsed.password and not parsed.query and not parsed.fragment
                 and not any(c.isspace() for c in endpoint))
        parsed.port
    except (ValueError, TypeError):
        valid = False
    if not valid:
        raise ValueError('A valid HTTP(S) API URL without credentials or query parameters is required')
    return Source(identifier, name.strip(), api_url=endpoint.rstrip('/'),
                  enabled=raw.get('enabled', True), tags=raw.get('tags', False),
                  search=search, pagination=pagination, chapter_languages=tuple(dict.fromkeys(languages)),
                  chapter_pagination=raw.get('chapter_pagination', False), image=image,
                  port=port, package=path.parent.name)


def load_packages(directory):
    sources, errors = [], []
    for path in sorted(Path(directory).glob('*/source.json')):
        try:
            sources.append(read_package(path))
        except (OSError, ValueError, TypeError) as exc:
            # Do not include raw JSON, URLs or credentials in error messages.
            message = 'Invalid JSON' if isinstance(exc, json.JSONDecodeError) else (
                'Manifest could not be read' if isinstance(exc, OSError) else str(exc))
            errors.append({'package': path.parent.name, 'message': message})
    return sources, errors


def registry(config):
    directory = config.get('SOURCE_PACKAGES_DIR') or Path(__file__).parent / 'sources'
    packages, errors = load_packages(directory)
    return {source.id: source for source in (*BUILTINS, *packages)}, errors
