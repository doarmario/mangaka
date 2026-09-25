"""Bounded HTTP transport and parsers for the public Demonic Scans pages."""
from collections import OrderedDict
from copy import deepcopy
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import re
from threading import RLock
from time import monotonic
from urllib.parse import urlencode, urljoin, urlsplit, parse_qs, unquote

from bs4 import BeautifulSoup
import requests

BASE_URL = "https://demonicscans.org"
IMAGE_HOSTS = {"demonicscans.org", "readermc.org", "cdn.demoniclibs.com"}
PAGE_HOSTS = {"readermc.org", "cdn.demoniclibs.com"}


class SourceError(Exception):
    def __init__(self, message, status=502, retry_after=None):
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after


def checked_url(url, image=False):
    """Only exact, known hosts; repeat this check after every redirect."""
    try:
        parsed = urlsplit(url)
        allowed = IMAGE_HOSTS if image else {urlsplit(BASE_URL).hostname}
        valid = (parsed.scheme == "https" and parsed.hostname in allowed
                 and parsed.port in (None, 443) and not parsed.username
                 and not parsed.password and not parsed.fragment)
    except (ValueError, TypeError):
        valid = False
    if not valid:
        raise SourceError("URL fora dos endereços permitidos.", 400)
    return url


def remote_id(url):
    parsed = urlsplit(checked_url(urljoin(BASE_URL, url)))
    if not re.fullmatch(r"/manga/[^/]+", parsed.path) or parsed.query:
        raise SourceError("Link de mangá inválido.")
    slug = parsed.path.removeprefix('/manga/')
    decoded = slug
    for _ in range(8):
        if decoded in {'.', '..'} or any(c in decoded for c in '/\\\r\n'):
            raise SourceError('Link de mangá inválido.', 400)
        new = unquote(decoded)
        if new == decoded:
            break
        decoded = new
    # Keep the original escaping: upstream uses repeatedly percent-encoded slugs.
    return parsed.path.removeprefix("/manga/").encode().hex()


def series_path(identifier):
    if not re.fullmatch(r"[0-9a-f]{2,1600}", identifier):
        raise SourceError("Identificador inválido.", 400)
    try:
        path = "/manga/" + bytes.fromhex(identifier).decode()
        if remote_id(path) != identifier or any(c in path for c in "\\\r\n"):
            raise ValueError()
    except (ValueError, UnicodeError):
        raise SourceError("Identificador inválido.", 400) from None
    return path


class Transport:
    def __init__(self):
        self.cooldown_until = 0
        self.lock = RLock()

    def get(self, url, *, image=False):
        with self.lock:
            remaining = self.cooldown_until - monotonic()
        if remaining > 0:
            raise SourceError("Fonte temporariamente indisponível.", 503, int(remaining) + 1)
        max_bytes = 20 * 1024 * 1024 if image else 4 * 1024 * 1024
        try:
            for _ in range(5):
                checked_url(url, image)
                # No cookie jar, retries, or execution of upstream JavaScript.
                with requests.get(url, timeout=(3, 20), allow_redirects=False, stream=True,
                                  headers={"User-Agent": "Mangaka-DemonicScans/0.1",
                                           "Referer": BASE_URL + "/"}) as response:
                    if response.status_code in (301, 302, 303, 307, 308):
                        location = response.headers.get("Location")
                        if not location:
                            raise SourceError("Redirecionamento inválido.")
                        url = urljoin(url, location)
                        continue
                    if response.status_code == 429:
                        wait = self.retry_seconds(response.headers.get("Retry-After", "60"))
                        self.pause(wait)
                        raise SourceError("Limite de consultas da fonte atingido.", 503, wait)
                    if response.status_code == 404:
                        raise SourceError("Conteúdo não encontrado na fonte.", 404)
                    if response.status_code != 200:
                        self.pause(30)
                        raise SourceError("Fonte temporariamente indisponível.", 503, 30)
                    content_type = response.headers.get("Content-Type", "").split(";")[0].lower()
                    permitted = {"image/jpeg", "image/png", "image/webp", "image/gif", "image/avif"}
                    if (image and content_type not in permitted) or (
                            not image and content_type not in {"text/html", "application/xhtml+xml"}):
                        raise SourceError("Tipo de conteúdo inesperado na fonte.")
                    chunks, size = [], 0
                    for chunk in response.iter_content(65536):
                        size += len(chunk)
                        if size > max_bytes:
                            raise SourceError("Resposta da fonte excedeu o limite de tamanho.")
                        chunks.append(chunk)
                    return b"".join(chunks), content_type
            raise SourceError("Excesso de redirecionamentos da fonte.")
        except requests.RequestException as exc:
            self.pause(30)
            raise SourceError("Não foi possível consultar a fonte.", 503, 30) from exc

    def pause(self, seconds):
        with self.lock:
            self.cooldown_until = max(self.cooldown_until, monotonic() + seconds)

    @staticmethod
    def retry_seconds(value):
        try:
            seconds = int(value)
        except (ValueError, TypeError):
            try:
                date = parsedate_to_datetime(value)
                seconds = int((date - datetime.now(timezone.utc)).total_seconds()) + 1
            except (ValueError, TypeError, OverflowError):
                seconds = 60
        return max(1, seconds)


class DemonicScans:
    def __init__(self, transport=None):
        self.transport = transport or Transport()
        self.cache = OrderedDict()
        self.lock = RLock()

    def cached(self, key, loader, ttl=900):
        # A single process shares misses and cooldown across gunicorn threads.
        with self.lock:
            entry = self.cache.get(key)
            if entry and entry[0] > monotonic():
                self.cache.move_to_end(key)
                return deepcopy(entry[1])
            value = loader()
            self.cache[key] = (monotonic() + ttl, deepcopy(value))
            self.cache.move_to_end(key)
            while len(self.cache) > 256:
                self.cache.popitem(last=False)
            return value

    def document(self, path, params=None):
        url = BASE_URL + path
        if params:
            url += "?" + urlencode(params)
        raw, _ = self.transport.get(url)
        return BeautifulSoup(raw, "html.parser")

    @staticmethod
    def text(node):
        return node.get_text(" ", strip=True) if node else ""

    def tags(self):
        def load():
            doc = self.document('/advanced.php')
            tags = [{'id': node['value'], 'name': self.text(node.find_parent('li'))}
                    for node in doc.select('input[name="genres[]"][value]')
                    if node['value'].isdigit()]
            if not tags or any(not tag['name'] for tag in tags):
                raise SourceError('A fonte não retornou os gêneros esperados.')
            return tags
        return self.cached('tags', load, 86400)

    def cards(self, doc, search=False):
        records = {}
        for link in doc.select('a[href^="/manga/"]' if search else '#advanced-content .advanced-element > a'):
            image = link.find('img')
            title = (self.text(link.select_one('.seach-right > div')) if search else
                     link.get('title') or (image.get('title') if image else None))
            if not title or not image:
                raise SourceError('A fonte retornou um título incompleto.')
            identifier = remote_id(link['href'])
            records[identifier] = {'id': identifier, 'title': title,
                                   'coverUrl': checked_url(urljoin(BASE_URL, image.get('src', '')), True)}
        return list(records.values())

    def search_records(self, query):
        def load():
            doc = self.document('/search.php', {'manga': query})
            records = self.cards(doc, search=True)
            # Empty searches return an empty fragment, not an HTML challenge page.
            if not records and (doc.find(['html', 'script', 'title']) or self.text(doc)):
                raise SourceError('A fonte retornou uma busca inesperada.')
            return records
        return self.cached(('search', query), load)

    def listing(self, page=1, query=None, tag=None):
        if tag and tag not in {item['id'] for item in self.tags()}:
            raise SourceError('Gênero inválido.', 400)
        if query and not tag:
            records = self.search_records(query)
            start = (page - 1) * 20
            return {'results': records[start:start + 20], 'total': len(records),
                    'has_next': start + 20 < len(records)}

        def load():
            params = {'list': page}
            if tag:
                params.update({'genre[]': tag, 'status': 'all', 'orderby': 'VIEWS DESC'})
            doc = self.document('/advanced.php', params)
            if not doc.select_one('#advanced-content'):
                raise SourceError('A fonte não retornou o catálogo esperado.')
            records = self.cards(doc)
            following = False
            for link in doc.select('.pagination a[href]'):
                values = parse_qs(urlsplit(link['href']).query).get('list', [])
                following |= any(value.isdigit() and int(value) > page for value in values)
            if query:
                matches = {item['id'] for item in self.search_records(query)}
                records = [item for item in records if item['id'] in matches]
            return {'results': records, 'total': None, 'has_next': following}
        return self.cached(('catalog', page, query, tag), load)

    def series(self, identifier):
        path = series_path(identifier)
        def load():
            doc = self.document(path)
            title = self.text(doc.select_one('#manga-info-rightColumn h1'))
            if not title or not doc.select_one('#chapters-list'):
                raise SourceError('A fonte não retornou o mangá esperado.')
            cover = doc.select_one('meta[property="og:image"]')
            stats = {}
            for row in doc.select('#manga-info-stats > div'):
                cells = row.find_all('li')
                if len(cells) == 2:
                    stats[self.text(cells[0]).rstrip(':').lower()] = self.text(cells[1])
            genres = [self.text(node) for node in doc.select('.genres-list li')]
            chapters = {}
            for link in doc.select('#chapters-list a.chplinks[href]'):
                parsed = urlsplit(checked_url(urljoin(BASE_URL, link['href'])))
                args = parse_qs(parsed.query)
                manga = args.get('manga', [''])[0]
                number = args.get('chapter', [''])[0]
                if parsed.path != '/chaptered.php' or not manga.isdigit() or not re.fullmatch(r'\d+(?:\.\d+)?', number):
                    raise SourceError('Link de capítulo inválido.')
                cid = manga + '-' + number
                chapters[cid] = {'id': cid, 'number': number, 'lang': 'en',
                                 'title': 'Chapter ' + number}
            author = stats.get('author', '')
            return {'id': identifier, 'title': title,
                    'description': self.text(doc.select_one('#manga-info-rightColumn .white-font')),
                    'genres': genres, 'authors': [author] if author and author.lower() != 'updating' else [],
                    'aliases': [name.strip() for name in stats.get('alternatives', '').split(';') if name.strip()],
                    'status': stats.get('status'),
                    'coverUrl': checked_url(urljoin(BASE_URL, cover['content']), True) if cover else None,
                    '_chapters': list(chapters.values())}
        return self.cached(('series', identifier), load)

    def info(self, identifier):
        result = self.series(identifier)
        result.pop('_chapters')
        names = {name.casefold() for name in result['genres']}
        result['tagLinks'] = [tag for tag in self.tags() if tag['name'].casefold() in names]
        return result

    def chapters(self, identifier):
        records = self.series(identifier)['_chapters']
        return {'chapters': records, 'total': len(records)}

    def pages(self, identifier, chapter_id):
        if chapter_id not in {item['id'] for item in self.series(identifier)['_chapters']}:
            raise SourceError('Capítulo não pertence a este mangá.', 404)
        def load():
            manga, number = chapter_id.split('-', 1)
            doc = self.document('/chaptered.php', {'manga': manga, 'chapter': number})
            pages = []
            for node in doc.select('img.imgholder[src]'):
                url = urljoin(BASE_URL, node['src'])
                if urlsplit(url).hostname not in PAGE_HOSTS:
                    continue  # The source injects an advertisement with this same CSS class.
                url = checked_url(url, True)
                if url not in pages:
                    pages.append(url)
            if not pages:
                raise SourceError('A fonte não retornou as páginas do capítulo.')
            return {'pages': pages}
        return self.cached(('pages', identifier, chapter_id), load, 600)
