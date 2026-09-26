"""Adapters for locally hosted external manga sources."""
from copy import deepcopy
from hashlib import sha256
import json
import re
from urllib.parse import quote, urlencode
from uuid import NAMESPACE_URL, uuid5

import requests
from flask import current_app
from sqlalchemy.exc import IntegrityError

from app import cache, db
from app.models import SourceReference
from app.libs.md import LANGUAGE_NAMES, Mangas

SOURCES = {'comick': 'ComicK', 'weebcentral': 'WeebCentral', 'asura': 'AsuraScans',
           'qiscans': 'Qi Scans', 'demonicscans': 'Demonic Scans', 'thunderscans': 'Thunder Scans'}
VISIBLE_SOURCES = {'asura': 'AsuraScans', 'qiscans': 'Qi Scans',
                   'demonicscans': 'Demonic Scans', 'thunderscans': 'Thunder Scans'}


def source_api_url(source):
    key = {'qiscans': 'QISCANS_API_URL', 'demonicscans': 'DEMONICSCANS_API_URL',
           'thunderscans': 'THUNDERSCANS_API_URL'}.get(
        source, 'MANGA_NOVEL_API_URL')
    return current_app.config.get(key, '').rstrip('/')


class SourceUnavailable(Exception):
    pass


def register_many(source, kind, records, parent_id=None):
    entries = []
    for remote_id, payload in records:
        identity = json.dumps([source, kind, parent_id, str(remote_id)])
        local_id = str(uuid5(NAMESPACE_URL, 'mangaka:' + identity))
        entries.append((local_id, str(remote_id), payload))
    if not entries:
        return []
    existing = {row.id: row for row in SourceReference.query.filter(
        SourceReference.id.in_([item[0] for item in entries])).all()}
    for local_id, remote_id, payload in entries:
        if local_id in existing:
            existing[local_id].payload = payload
            continue
        # A second worker can discover the same result at the same time.
        try:
            with db.session.begin_nested():
                row = SourceReference(id=local_id, source=source, kind=kind,
                                      remote_id=remote_id, parent_id=parent_id, payload=payload)
                db.session.add(row)
                db.session.flush()
                existing[local_id] = row
        except IntegrityError:
            existing[local_id] = db.session.get(SourceReference, local_id)
    db.session.commit()
    return [existing[item[0]] for item in entries]


class MangaNovel:
    limit = 20

    def __init__(self, source):
        if source not in SOURCES:
            raise ValueError('Unknown source')
        self.source = source
        self.base = source_api_url(source)
        if not self.base:
            raise SourceUnavailable('A API adicional não está configurada.')

    def _request(self, path, **params):
        params = {'source': self.source, **params}
        digest = sha256(json.dumps([self.base, path, params], sort_keys=True).encode()).hexdigest()
        key = ('manga_novel_v3_' if self.source == 'qiscans' else 'manga_novel_v2_') + digest
        cached = cache.get(key)
        if cached is not None:
            return deepcopy(cached)
        cooldown = 'manga_novel_unavailable_' + self.source
        if cache.get(cooldown):
            raise SourceUnavailable(f'{SOURCES[self.source]} indisponível. Tente novamente em instantes.')
        try:
            response = requests.get(self.base + path, params=params, timeout=(3, 30))
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict) or data.get('error'):
                raise ValueError('Invalid API response')
            # Do not silently accept the original server's MangaDex fallback.
            if data.get('source') != self.source:
                raise ValueError('Unexpected provider returned by API')
        except (requests.RequestException, ValueError) as exc:
            cache.set(cooldown, True, timeout=30)
            raise SourceUnavailable(f'{SOURCES[self.source]} indisponível. Tente novamente em instantes.') from exc
        cache.set(key, data, timeout=600 if path.endswith('/pages') else 900)
        return deepcopy(data)

    @staticmethod
    def _remote(record):
        return record.get('id') or record.get('hid') or record.get('slug')

    def search(self, query, page=1, tag=None):
        if tag:
            return self.catalog(page, tag=tag, query=query)
        if self.source in {'demonicscans', 'thunderscans'}:
            return self.catalog(page, query=query)
        # Asura returns a complete search, independent of the page argument.
        response = self._request('/api/manga/search', q=query, page=1 if self.source == 'asura' else page, limit=self.limit)
        records = response.get('results', [])
        if not isinstance(records, list):
            raise SourceUnavailable('A fonte retornou uma lista inválida.')
        total = len(records) if self.source == 'asura' else None
        if self.source == 'qiscans':
            return self._qiscans_list(response)
        if self.source == 'asura':
            records = records[(page - 1) * self.limit:page * self.limit]
        return self._normalize_list(records, total, page * self.limit < total if total is not None else len(records) >= self.limit)

    def tags(self):
        if self.source not in {'asura', 'qiscans', 'demonicscans', 'thunderscans'}:
            return []
        response = self._request('/api/manga/tags')
        return response.get('tags', [])

    def catalog(self, page=1, tag=None, query=None):
        filters = {}
        if tag:
            filters['tag'] = tag
        if query:
            filters['q'] = query
        response = self._request('/api/manga/catalog', page=page, limit=self.limit, **filters)
        if self.source == 'qiscans':
            return self._qiscans_list(response)
        records = response.get('results')
        total = response.get('total')
        if not isinstance(records, list) or (total is not None and (not isinstance(total, int) or total < 0)):
            raise SourceUnavailable('A fonte retornou um catálogo inválido.')
        return self._normalize_list(records, total, bool(response.get('has_next')))

    def _qiscans_list(self, response):
        records = response.get('results')
        total, pages = response.get('total'), response.get('total_pages')
        page, size = response.get('page'), response.get('page_size')
        if (not isinstance(records, list) or any(type(n) is not int for n in (total, pages, page, size))
                or total < 0 or size < 1 or not 1 <= page <= pages
                or pages != max(1, (total + size - 1) // size)
                or type(response.get('has_next')) is not bool
                or response['has_next'] != (page < pages)):
            raise SourceUnavailable('A fonte retornou totais ou paginação inválidos.')
        result = self._normalize_list(records, total, response['has_next'])
        return {**result, 'total_pages': pages, 'page': page}

    def _normalize_list(self, records, total, has_next):
        records = [record for record in records if self._remote(record) and record.get('title')]
        refs = register_many(self.source, 'manga', [(self._remote(r), r) for r in records])
        return {'itens': [{'id': ref.id, 'title': ref.payload['title'], 'source_name': SOURCES[self.source]} for ref in refs],
                'total': total, 'has_next': has_next}

    def info(self, ref):
        # ComicK accepts the slug for details and hid for chapter lists.
        remote = ref.payload.get('slug') if self.source == 'comick' else None
        raw = self._request('/api/manga/' + quote(remote or ref.remote_id, safe=''))
        return {'id': ref.id, 'title': raw.get('title') or ref.payload.get('title', 'Sem título'),
                'sinopse': raw.get('description') or 'Sem descrição', 'tags': raw.get('genres') or [],
                'tag_links': raw.get('tagLinks') or [], 'aliases': raw.get('aliases') or [],
                'autor': ', '.join(raw.get('authors') or []), 'ano': raw.get('year'),
                'status': str(raw.get('status') or 'Não informado'),
                'cover_url': raw.get('coverUrl') or ref.payload.get('coverUrl'),
                'source_name': SOURCES[self.source]}

    def chapters(self, ref):
        records = []
        languages = ('pt-br', 'pt', 'en') if self.source == 'comick' else ('en',)
        for language in languages:
            page = 1
            seen = set()
            while True:
                response = self._request('/api/manga/' + quote(ref.remote_id, safe='') + '/chapters',
                                         lang=language, page=page, limit=100)
                batch = response.get('chapters', [])
                if not isinstance(batch, list):
                    raise SourceUnavailable('A fonte retornou capítulos inválidos.')
                fresh = [r for r in batch if self._remote(r) and self._remote(r) not in seen]
                for item in fresh:
                    seen.add(self._remote(item))
                    actual_language = item.get('lang', language)
                    if actual_language not in LANGUAGE_NAMES:
                        continue
                    number = item.get('number')
                    if number is None or number == '':
                        number = item.get('chap')
                    if number is None or number == '':
                        match = re.search(r'(?:chapter|cap[ií]tulo)\s*([\d.]+)', item.get('title', ''), re.I)
                        number = match.group(1) if match else 'Sem número'
                    records.append((self._remote(item), {'cap': str(number), 'language': actual_language,
                                    'language_name': LANGUAGE_NAMES[actual_language]}))
                total = response.get('total')
                if self.source != 'comick' or not batch or (isinstance(total, int) and page * 100 >= total):
                    break
                if not fresh or page >= 100:
                    raise SourceUnavailable('A fonte não permitiu carregar todos os capítulos.')
                page += 1
        refs = register_many(self.source, 'chapter', records, parent_id=ref.id)
        result = [{**r.payload, 'cap_id': r.id, 'is_readed': False, 'others': []} for r in refs]
        return sorted(result, key=Mangas._chapter_order, reverse=True)

    def image_proxy_url(self, url):
        if not isinstance(url, str) or not url.startswith(('https://', 'http://')):
            return '/static/img/cover-placeholder.svg'
        return self.base + '/api/proxy/image?' + urlencode({'url': url})

    def pages(self, ref, parent):
        path = '/api/manga/' + quote(parent.remote_id, safe='') + '/chapters/' + quote(ref.remote_id, safe='') + '/pages'
        result = self._request(path).get('pages', [])
        urls = [item if isinstance(item, str) else item.get('url', '') for item in result]
        return ['/img/page/proxy?' + urlencode({'url': self.image_proxy_url(url)}) for url in urls if url]
