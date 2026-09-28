"""Federated discovery backed by the local canonical catalog."""
from hashlib import sha256
from itertools import zip_longest

import requests
from mangadex.errors import ApiError
from app import cache
from app.libs.manga_novel import MangaNovel, SourceUnavailable


from app.libs.identity import title_keys as titles, match_confidence, source_work_key


def matches(left, right):
    return match_confidence(left, right)[0] == 1.0


def same_source_record(left, right):
    return left['source_id'] == right['source_id'] and source_work_key(
        left['source_id'], left.get('external_id') or left['id']) == source_work_key(
        right['source_id'], right.get('external_id') or right['id'])


def group_results(items):
    """Only group unambiguous, exact titles/aliases across distinct sources."""
    groups = []
    for item in items:
        candidates = [g for g in groups if matches(g, item)]
        # Check the entire batch, so duplicate titles within one provider never
        # get silently assigned to an unrelated edition from another provider.
        ambiguous = any(not same_source_record(other, item) and other['source_id'] == item['source_id']
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
            raise SourceUnavailable('The sources are unavailable. Please try again shortly.')
        items = [item for row in zip_longest(*batches) for item in row if item]
        from app.libs.canonical import resolve_work, canonical_work
        from app import db
        grouped = group_results(items)
        for group in grouped:
            for item in group['sources']:
                sw = resolve_work(item, item['source_id'], allow_title_match=not group['ambiguous'])
                item['work_id'] = sw.work_id
            group['work_id'] = group['sources'][0]['work_id']
        db.session.commit()
        persisted = {}
        for group in grouped:
            for item in group['sources']:
                identity = canonical_work(item['work_id']).id
                if identity not in persisted:
                    persisted[identity] = {**item, 'work_id': identity, 'sources': []}
                persisted[identity]['sources'].append(item)
        return {'itens': list(persisted.values()), 'unavailable': unavailable, 'has_next': has_next}

    def alternatives(self, identifier):
        sources = self.library.sources()
        key = 'cross-source-v2:' + sha256(repr((identifier, sources)).encode()).hexdigest()
        stored = cache.get(key)
        if stored is not None:
            return stored
        ref = self.library.reference(identifier, 'manga')
        source = ref.source if ref else 'mangadex'
        from app.models import SourceWork
        from app.libs.canonical import work_data
        from app import db
        known = db.session.get(SourceWork, identifier)
        try:
            item = MangaNovel(source).info(ref) if ref else self.library.getManga(identifier)
        except (SourceUnavailable, ApiError, requests.RequestException):
            if known is None:
                raise
            item = {**work_data(known.work), 'id': identifier}
        from app.libs.canonical import resolve_work
        from app import db
        origin = known or resolve_work(item, source)
        db.session.commit()
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
                    sw = resolve_work(candidates[0], target)
                    db.session.commit()
                    from app.libs.canonical import canonical_work
                    if canonical_work(sw.work_id).id != canonical_work(origin.work_id).id:
                        continue
                    found.append({'id': candidates[0]['id'], 'work_id': sw.work_id, 'source_id': target, 'source_name': name})
            except (SourceUnavailable, ApiError, requests.RequestException):
                unavailable.append(name)
        data = {'sources': found, 'unavailable': unavailable}
        cache.set(key, data, timeout=60 if unavailable else 3600)
        return data
