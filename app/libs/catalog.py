"""Federated discovery without merging provider IDs or reading histories."""
import unicodedata
from hashlib import sha256
from itertools import zip_longest

import requests
from mangadex.errors import ApiError
from app import cache
from app.libs.manga_novel import MangaNovel, SourceUnavailable


def titles(item):
    values = [item.get('title', ''), *item.get('aliases', [])]
    return {normalized for value in values if isinstance(value, str)
            if (normalized := ' '.join(''.join(
                c if c.isalnum() else ' ' for c in unicodedata.normalize('NFKC', value).casefold()
            ).split())) not in {'', 'sem título', 'untitled'}}


def matches(left, right):
    if left.get('ano') and right.get('ano') and left['ano'] != right['ano']:
        return False
    return bool(titles(left) & titles(right))


def group_results(items):
    """Only group unambiguous, exact titles/aliases across distinct sources."""
    groups = []
    for item in items:
        candidates = [g for g in groups if matches(g, item)]
        # Check the entire batch, so duplicate titles within one provider never
        # get silently assigned to an unrelated edition from another provider.
        ambiguous = any(other['id'] != item['id'] and other['source_id'] == item['source_id']
                        and matches(other, item) for other in items)
        if len(candidates) == 1 and not ambiguous and not candidates[0]['ambiguous'] and all(
                source['source_id'] != item['source_id'] for source in candidates[0]['sources']):
            candidates[0]['sources'].append(item)
        else:
            groups.append({**item, 'sources': [item], 'ambiguous': ambiguous})
    return groups


class UnifiedCatalog:
    def __init__(self, library):
        self.library = library

    def provider(self, source, query, page):
        if source == 'mangadex':
            offset = (page - 1) * self.library.limit
            result = (self.library.searchMangaByTitle(query, offset) if query
                      else self.library.listaGeral(offset))
            return {**result, 'has_next': page * self.library.limit < min(result['total'], 10000)}
        adapter = MangaNovel(source)
        return adapter.search(query, page) if query else adapter.catalog(page)

    def listing(self, query=None, page=1):
        batches, unavailable, has_next = [], [], False
        sources = self.library.sources()
        for source, name in sources.items():
            try:
                result = self.provider(source, query, page)
            except (SourceUnavailable, ApiError, requests.RequestException):
                unavailable.append(name)
                continue
            # Some providers clamp out-of-range pages to the last page.
            if result.get('page', page) != page:
                continue
            batches.append([{**item, 'source_id': source, 'source_name': name}
                            for item in result['itens']])
            has_next |= result['has_next']
        if len(unavailable) == len(sources):
            raise SourceUnavailable('As fontes estão indisponíveis. Tente novamente em instantes.')
        items = [item for row in zip_longest(*batches) for item in row if item]
        return {'itens': group_results(items), 'unavailable': unavailable, 'has_next': has_next}

    def alternatives(self, identifier):
        sources = self.library.sources()
        key = 'cross-source-v1:' + sha256(repr((identifier, sources)).encode()).hexdigest()
        stored = cache.get(key)
        if stored is not None:
            return stored
        ref = self.library.reference(identifier, 'manga')
        source = ref.source if ref else 'mangadex'
        item = MangaNovel(source).info(ref) if ref else self.library.getManga(identifier)
        found, unavailable = [], []
        # Limit requests: one title search per other provider, with provider and
        # aggregate caches. Prefer an English alias when MangaDex has one.
        query = item.get('search_title') or item['title']
        for target, name in sources.items():
            if target == source:
                continue
            try:
                result = self.provider(target, query, 1)
                candidates = [other for other in result['itens'] if matches(item, other)]
                if len(candidates) == 1:
                    found.append({'id': candidates[0]['id'], 'source_id': target, 'source_name': name})
            except (SourceUnavailable, ApiError, requests.RequestException):
                unavailable.append(name)
        data = {'sources': found, 'unavailable': unavailable}
        cache.set(key, data, timeout=60 if unavailable else 3600)
        return data
