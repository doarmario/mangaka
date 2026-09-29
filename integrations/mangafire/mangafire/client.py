"""Bounded API transport and translation into Mangaka's source contract."""
from collections import OrderedDict
from copy import deepcopy
import json
import re
from threading import RLock
from time import monotonic
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup
import requests

from .signature import signed_path

BASE_URL = 'https://mangafire.to'
CDN_DOMAINS = ('mfcdn.nl', 'mfcdn2.xyz', 'mfcdn3.xyz')
LANGUAGES = ('pt-br', 'en')


class SourceError(Exception):
    def __init__(self, message, status=502, retry_after=None):
        super().__init__(message)
        self.status, self.retry_after = status, retry_after


def checked_url(url, image=False):
    try:
        parsed = urlsplit(url)
        host = parsed.hostname or ''
        allowed = (any(host == domain or host.endswith('.' + domain) for domain in CDN_DOMAINS)
                   if image else host == 'mangafire.to')
        valid = (parsed.scheme == 'https' and allowed and parsed.port in (None, 443)
                 and not parsed.username and not parsed.password and not parsed.fragment
                 and not any(ord(c) < 32 or c.isspace() for c in url))
    except (TypeError, ValueError, AttributeError):
        valid = False
    if not valid:
        raise SourceError('URL is outside the permitted source hosts.', 400)
    return url


def identifier(value, chapter=False):
    pattern = r'[0-9]{1,20}' if chapter else r'[a-zA-Z0-9]{1,64}'
    if not isinstance(value, str) or not re.fullmatch(pattern, value):
        raise SourceError('Invalid content identifier.', 400)
    return value


class Transport:
    def __init__(self):
        self.lock = RLock()
        self.cooldown_until = 0

    def get(self, url, *, image=False):
        with self.lock:
            remaining = self.cooldown_until - monotonic()
        if remaining > 0:
            raise SourceError('MangaFire is temporarily unavailable.', 503, int(remaining) + 1)
        try:
            for _ in range(5):
                checked_url(url, image)
                with requests.get(url, timeout=(3, 20), allow_redirects=False, stream=True,
                                  headers={'User-Agent': 'Mangaka-MangaFire/0.1',
                                           'Referer': BASE_URL + '/', 'Accept': '*/*' if image else 'application/json'}) as response:
                    if response.status_code in (301, 302, 303, 307, 308):
                        if not response.headers.get('Location'):
                            raise SourceError('Invalid upstream redirect.')
                        url = urljoin(url, response.headers['Location'])
                        continue
                    if response.status_code == 404:
                        raise SourceError('Content was not found on MangaFire.', 404)
                    if response.status_code != 200:
                        try:
                            wait = max(30, min(int(response.headers.get('Retry-After', 60)), 300))
                        except ValueError:
                            wait = 60
                        with self.lock:
                            self.cooldown_until = monotonic() + wait
                        raise SourceError('MangaFire rejected the request. Please try again later.', 503, wait)
                    content_type = response.headers.get('Content-Type', '').split(';')[0].lower()
                    allowed = {'image/jpeg', 'image/png', 'image/webp', 'image/gif', 'image/avif'} if image else {'application/json'}
                    if content_type not in allowed:
                        raise SourceError('MangaFire returned an unexpected content type.')
                    maximum = 20 * 1024 * 1024 if image else 4 * 1024 * 1024
                    chunks, size = [], 0
                    for chunk in response.iter_content(65536):
                        size += len(chunk)
                        if size > maximum:
                            raise SourceError('Upstream response exceeds the size limit.')
                        chunks.append(chunk)
                    return b''.join(chunks), content_type
            raise SourceError('Too many upstream redirects.')
        except requests.RequestException as exc:
            with self.lock:
                self.cooldown_until = monotonic() + 30
            raise SourceError('MangaFire could not be reached.', 503, 30) from exc


class MangaFire:
    def __init__(self, transport=None):
        self.transport = transport or Transport()
        self.cache = OrderedDict()
        self.lock = RLock()

    def api(self, path, params=()):
        url = BASE_URL + signed_path(path, params)
        # Serialize cold metadata fetches and bound the cache. Images are never
        # stored here; they pass through the image proxy only on request.
        with self.lock:
            cached = self.cache.get(url)
            if cached and cached[0] > monotonic():
                self.cache.move_to_end(url)
                return deepcopy(cached[1])
            body, _ = self.transport.get(url)
            try:
                data = json.loads(body)
            except (ValueError, UnicodeError) as exc:
                raise SourceError('MangaFire returned invalid JSON.') from exc
            if not isinstance(data, dict) or ('data' not in data and 'items' not in data):
                raise SourceError('MangaFire returned an unexpected API response.')
            self.cache[url] = (monotonic() + (300 if path.startswith('/chapters/') else 900), data)
            self.cache.move_to_end(url)
            while len(self.cache) > 128:
                self.cache.popitem(last=False)
            return deepcopy(data)

    @staticmethod
    def items(data):
        items = data.get('items')
        meta = data.get('meta')
        if (not isinstance(items, list) or any(not isinstance(item, dict) for item in items)
                or not isinstance(meta, dict) or type(meta.get('total')) is not int
                or meta['total'] < 0 or type(meta.get('hasNext')) is not bool):
            raise SourceError('MangaFire returned invalid pagination.')
        return items, meta

    @staticmethod
    def record(raw):
        hid = identifier(str(raw.get('hid', '')))
        title = raw.get('title')
        if not isinstance(title, str) or not title.strip():
            raise SourceError('MangaFire returned a title without a name.')
        poster = raw.get('poster') or {}
        cover = poster.get('large') or poster.get('medium') or ''
        if cover:
            checked_url(cover, image=True)
        return {'id': hid, 'title': title, 'coverUrl': cover,
                'url': BASE_URL + '/title/' + hid, 'type': raw.get('type') or 'manga'}

    def listing(self, page=1, query=None, tag=None):
        params = [('page', str(page)), ('limit', '20'),
                  ('order[relevance]' if query else 'order[chapter_updated_at]', 'desc')]
        if query:
            params.append(('keyword', query))
        if tag:
            match = re.fullmatch(r'(genre|theme|demographic):([0-9]{1,10})', tag)
            if not match:
                raise SourceError('Invalid tag.', 400)
            field = {'genre': 'genres_in[0]', 'theme': 'theme_ids[0]', 'demographic': 'demographics[0]'}[match[1]]
            params.append((field, match[2]))
        raw, meta = self.items(self.api('/titles', params))
        return {'results': [self.record(item) for item in raw], 'total': meta['total'],
                'has_next': meta['hasNext'], 'page': page, 'page_size': 20,
                'total_pages': max(1, (meta['total'] + 19) // 20)}

    def tags(self):
        data = self.api('/filter-options').get('data')
        if not isinstance(data, dict):
            raise SourceError('MangaFire returned invalid filters.')
        result = []
        for group, kind in [('genres', 'genre'), ('themes', 'theme'), ('demographics', 'demographic')]:
            for item in data.get(group, []):
                result.append({'id': f"{kind}:{item['id']}", 'name': item['name']})
        return result

    def info(self, hid):
        raw = self.api('/titles/' + identifier(hid)).get('data')
        if not isinstance(raw, dict) or raw.get('hid') != hid:
            raise SourceError('MangaFire returned an unexpected title.')
        result = self.record(raw)
        aliases = [title for title in raw.get('altTitles', []) if isinstance(title, str) and title.strip()]
        tags = []
        for group, kind in [('genres', 'genre'), ('themes', 'theme'), ('demographics', 'demographic')]:
            tags.extend({'id': f"{kind}:{t['id']}", 'name': t['title']} for t in raw.get(group, []))
        external = {}
        for field, provider in [('malId', 'myanimelist'), ('anilistId', 'anilist')]:
            value = str(raw.get(field) or '')
            if value.isdecimal():
                external[provider] = value
        links = raw.get('links') or {}
        match = re.fullmatch(r'https://mangadex\.org/title/([0-9a-f-]{36})/?', links.get('md', ''))
        if match:
            external['mangadex'] = match[1]
        return {**result, 'description': BeautifulSoup(raw.get('synopsisHtml') or '', 'html.parser').get_text(' ', strip=True),
                'aliases': aliases, 'titles': [{'title': t, 'language': 'und'} for t in [result['title'], *aliases]],
                'authors': [a['title'] for a in raw.get('authors', [])],
                'artist': ', '.join(a['title'] for a in raw.get('artists', [])),
                'year': raw.get('year'), 'genres': [t['name'] for t in tags], 'tagLinks': tags,
                'status': {'releasing': 'ongoing', 'finished': 'completed', 'on_hiatus': 'hiatus',
                           'discontinued': 'cancelled'}.get(raw.get('status'), 'unknown'),
                'external_ids': external}

    def chapters(self, hid, language='en', page=1):
        identifier(hid)
        if language not in LANGUAGES:
            raise SourceError('Unsupported chapter language.', 400)
        raw, meta = self.items(self.api('/titles/' + hid + '/chapters', [
            ('language', language), ('sort', 'number'), ('order', 'desc'), ('page', str(page)), ('limit', '100')]))
        result = []
        for item in raw:
            if item.get('language') != language:
                raise SourceError('MangaFire returned chapters in an unexpected language.')
            result.append({'id': identifier(str(item.get('id', '')), chapter=True),
                           'number': str(item['number']), 'title': item.get('name'), 'lang': language})
        return {'chapters': result, 'total': meta['total']}

    def pages(self, hid, chapter):
        identifier(hid)
        raw = self.api('/chapters/' + identifier(chapter, chapter=True)).get('data')
        if not isinstance(raw, dict) or str(raw.get('id')) != chapter or (raw.get('title') or {}).get('hid') != hid:
            raise SourceError('Chapter does not belong to this title.', 404)
        if raw.get('language') not in LANGUAGES:
            raise SourceError('Unsupported chapter language.', 400)
        pages = raw.get('pages')
        if not isinstance(pages, list) or not pages or len(pages) > 1000:
            raise SourceError('MangaFire returned invalid chapter pages.')
        return {'pages': [checked_url(p.get('url', ''), image=True) for p in pages]}
