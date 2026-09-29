"""Federated discovery backed by the local canonical catalog."""
from hashlib import sha256
from itertools import zip_longest
from copy import deepcopy
from uuid import uuid4
from time import monotonic, sleep

import requests
from flask import current_app
from mangadex.errors import ApiError
from app import cache
from app.libs.manga_novel import MangaNovel, SourceUnavailable
from app.libs.source_registry import configuration_signature


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
        result = None
        for result in self.iter_listing(query, page):
            pass
        return result

    def iter_listing(self, query=None, page=1):
        from app.libs.source_loading import provider_results
        sources = self.library.sources()
        settings = configuration_signature()
        key = 'unified-listing-v1:' + sha256(repr((query, page, sources, settings,
            self.library.languages, self.library.langs, self.library.limit)).encode()).hexdigest()
        stored = cache.get(key)
        if stored is not None:
            result = deepcopy(stored)
            result['itens'] = self.persisted_items([s for item in result['itens'] for s in item['sources']])
            yield result
            return
        token = str(uuid4())
        lock = key + ':loading'
        if not cache.add(lock, token, timeout=120):
            # Readers of the same page share the in-flight refresh instead of
            # each issuing another batch of upstream requests.
            owner, seen, deadline = cache.get(lock), None, monotonic() + 40
            yield {'waiting': True}
            while monotonic() < deadline:
                finished = cache.get(key)
                progress = cache.get(key + ':progress')
                if finished is not None:
                    finished = deepcopy(finished)
                    finished['itens'] = self.persisted_items([s for item in finished['itens'] for s in item['sources']])
                    yield finished
                    return
                if progress and progress['owner'] == owner and progress['result']['completed'] != seen:
                    snapshot = deepcopy(progress['result'])
                    seen = snapshot['completed']
                    yield snapshot
                if cache.get(lock) != owner:
                    break
                sleep(.25)
            raise SourceUnavailable('Some sources did not finish loading. Please try again.')
        batches, unavailable, completed, has_next = {}, [], [], False
        try:
            for source, result in provider_results(self, sources, query, page):
                completed.append(source)
                if result is None:
                    unavailable.append(sources[source])
                elif result.get('page', page) == page:
                    batches[source] = [{**item, 'source_id': source, 'source_name': sources[source]}
                                       for item in result['itens']]
                    has_next |= result['has_next']
                items = self.resolve_batches([batches[s] for s in sources if s in batches])
                final = len(completed) == len(sources)
                if final and len(unavailable) == len(sources):
                    raise SourceUnavailable('The sources are unavailable. Please try again shortly.')
                snapshot = {'itens': items, 'unavailable': list(unavailable), 'has_next': has_next,
                            'completed': len(completed), 'total_sources': len(sources), 'done': final}
                cache.set(key + ':progress', {'owner': token, 'result': snapshot}, timeout=120)
                if final:
                    cache.set(key, snapshot, timeout=30 if unavailable else 120)
                yield snapshot
        finally:
            if cache.get(lock) == token:
                cache.delete(lock)

    def resolve_batches(self, batches):
        items = [item for row in zip_longest(*batches) for item in row if item]
        from app.libs.canonical import resolve_work
        from app import db
        grouped = group_results(items)
        for group in grouped:
            for item in group['sources']:
                sw = resolve_work(item, item['source_id'], allow_title_match=not group['ambiguous'])
                item['work_id'] = sw.work_id
            group['work_id'] = group['sources'][0]['work_id']
        db.session.commit()
        return self.persisted_items(items)

    @staticmethod
    def persisted_items(items):
        from app.libs.canonical import canonical_work
        persisted = {}
        for item in items:
            identity = canonical_work(item['work_id']).id
            if identity not in persisted:
                persisted[identity] = {**item, 'work_id': identity, 'sources': []}
            persisted[identity]['sources'].append(item)
        return list(persisted.values())

    def alternatives(self, identifier):
        sources = self.library.sources()
        signature = (identifier, sources, configuration_signature())
        key = 'cross-source-v2:' + sha256(repr(signature).encode()).hexdigest()
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
        from app.libs.source_loading import provider_results
        targets = {key: name for key, name in sources.items() if key != source}
        for target, result in provider_results(self, targets, query, 1):
            name = sources[target]
            if result is not None:
                candidates = [other for other in result['itens'] if matches(item, other)]
                if len(candidates) == 1:
                    sw = resolve_work(candidates[0], target)
                    db.session.commit()
                    from app.libs.canonical import canonical_work
                    if canonical_work(sw.work_id).id != canonical_work(origin.work_id).id:
                        continue
                    found.append({'id': candidates[0]['id'], 'work_id': sw.work_id, 'source_id': target, 'source_name': name})
            else:
                unavailable.append(name)
        data = {'sources': found, 'unavailable': unavailable}
        cache.set(key, data, timeout=60 if unavailable else 3600)
        return data
