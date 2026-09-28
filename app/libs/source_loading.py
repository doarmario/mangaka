"""Bounded provider I/O; each task owns its Flask context and database session."""
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
from threading import BoundedSemaphore

from flask import current_app
import requests
from mangadex.errors import ApiError
from app.libs.manga_novel import SourceUnavailable, MangaNovel, defer_source_registration

_pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix='mangaka-source')
_slots = BoundedSemaphore(6)


def provider_results(catalog, sources, query, page):
    app = current_app._get_current_object()
    futures = {}

    def fetch(source):
        with app.app_context():
            token = defer_source_registration.set(True)
            try:
                return catalog.provider(source, query, page)
            finally:
                defer_source_registration.reset(token)

    try:
        for source in sources:
            if not _slots.acquire(blocking=False):
                yield source, None
                continue
            try:
                future = _pool.submit(fetch, source)
            except Exception:
                _slots.release()
                raise
            future.add_done_callback(lambda _: _slots.release())
            futures[future] = source
        try:
            for future in as_completed(tuple(futures), timeout=35):
                source = futures.pop(future)
                try:
                    result = future.result()
                except (SourceUnavailable, ApiError, requests.RequestException):
                    result = None
                if result is not None and '_records' in result:
                    records = result.pop('_records')
                    result.update(MangaNovel(source)._normalize_list(
                        records, result['total'], result['has_next']))
                yield source, result
        except TimeoutError:
            for source in futures.values():
                yield source, None
    finally:
        for future in futures:
            future.cancel()
