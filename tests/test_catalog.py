import pytest
import json
from threading import Event
from app.libs.catalog import UnifiedCatalog, group_results, matches
from app.libs.library import Library
from app.libs.manga_novel import MangaNovel, SourceUnavailable


def item(identifier, title, source='mangadex', **extra):
    return dict(id=identifier, title=title, source_id=source, source_name=source, **extra)


def test_exact_alias_matching_keeps_sequels_and_ambiguous_editions_separate():
    original = item('a', 'Título', aliases=['Solo Leveling'])
    other = item('b', 'SOLO  LEVELING', 'asura')
    sequel = item('c', 'Solo Leveling Ragnarok', 'asura')
    assert len(group_results([original, other, sequel])) == 2
    assert len(group_results([original, other])[0]['sources']) == 2
    assert len(group_results([original, other, {**other, 'id': 'd'}])) == 3
    assert not matches(item('a', 'Story', ano=2020), item('b', 'Story', ano=2024))


@pytest.fixture
def unified(app, monkeypatch):
    monkeypatch.setattr(Library, 'sources', staticmethod(lambda: {'mangadex': 'MangaDex', 'asura': 'AsuraScans'}))
    def provider(self, source, query, page):
        return {'itens': [item(source, 'Shared title', source)], 'has_next': page == 1}
    monkeypatch.setattr(UnifiedCatalog, 'provider', provider)
    return app.test_client()


def test_default_search_and_catalog_combine_sources(unified):
    for path in ('/search?query=Shared&load=sync', '/mangas?load=sync'):
        result = unified.get(path)
        assert result.status_code == 200
        assert result.text.count('class="manga-card"') == 1
        assert 'MangaDex · AsuraScans' in result.text
        assert 'source=all' in result.text


def test_partial_failure_keeps_working_source(unified, monkeypatch):
    def provider(self, source, query, page):
        if source == 'asura':
            raise SourceUnavailable('down')
        return {'itens': [item('a', 'Still available')], 'has_next': False}
    monkeypatch.setattr(UnifiedCatalog, 'provider', provider)
    result = unified.get('/search?query=test&load=sync')
    assert result.status_code == 200
    assert 'Still available' in result.text
    assert 'Could not reach: AsuraScans' in result.text


def test_all_failures_report_unavailability(unified, monkeypatch):
    def fail(*args):
        raise SourceUnavailable('down')
    monkeypatch.setattr(UnifiedCatalog, 'provider', fail)
    assert unified.get('/mangas?load=sync').status_code == 503


def test_clamped_provider_page_does_not_repeat_titles(unified, monkeypatch, context):
    monkeypatch.setattr(UnifiedCatalog, 'provider', lambda *a: {
        'itens': [item('a', 'Repeated')], 'has_next': False, 'page': 1})
    assert UnifiedCatalog(Library()).listing(page=2)['itens'] == []


def test_detail_source_lookup_is_cached(unified, monkeypatch):
    calls = []
    monkeypatch.setattr(Library, 'getManga', lambda *a: item('id', 'Português', aliases=['Shared title'], search_title='Shared title'))
    def provider(self, source, query, page):
        calls.append(query)
        return {'itens': [item('external', 'Shared title', 'asura')]}
    monkeypatch.setattr(UnifiedCatalog, 'provider', provider)
    first = unified.get('/manga/id/sources')
    assert first.status_code == 200
    assert first.json['sources'][0]['url'] == '/manga/external'
    assert unified.get('/manga/id/sources').json == first.json
    assert calls == ['Shared title']


def test_explicit_mangadex_pagination_preserves_provider(unified, monkeypatch):
    monkeypatch.setattr(Library, 'getTotalPages', lambda *a, **kw: 40)
    monkeypatch.setattr(Library, 'listaGeral', lambda *a, **kw: {'itens': [], 'total': 40})
    result = unified.get('/mangas?source=mangadex')
    assert result.status_code == 200
    assert '/mangas/2?source=mangadex' in result.text
    blank = unified.get('/search?query=&source=mangadex')
    assert blank.location.endswith('/mangas?source=mangadex')


def test_rotated_asura_urls_share_one_canonical_card(unified, monkeypatch):
    def provider(self, source, query, page):
        if source == 'asura':
            return {'itens': [item(token, 'Shared title', source,
                                  external_id='comics/shared-title-' + token)
                              for token in ('05c7df14', '3ec3b16f')], 'has_next': False}
        return {'itens': [item('md', 'Shared title')], 'has_next': False}
    monkeypatch.setattr(UnifiedCatalog, 'provider', provider)
    for _ in range(2):
        response = unified.get('/mangas?load=sync')
        assert response.status_code == 200
        assert response.text.count('class="manga-card"') == 1
        assert 'MangaDex · AsuraScans' in response.text
        assert 'AsuraScans · AsuraScans' not in response.text


def test_catalog_shell_does_not_wait_for_providers(unified, monkeypatch):
    def forbidden(*args):
        pytest.fail('The HTML shell must not make provider requests')
    monkeypatch.setattr(UnifiedCatalog, 'provider', forbidden)
    for path in ('/mangas', '/search?query=Shared'):
        response = unified.get(path)
        assert response.status_code == 200
        assert 'data-catalog-stream=' in response.text
        assert 'Load catalog without JavaScript' in response.text


def test_stream_exposes_fast_results_before_slow_source_and_then_deduplicates(unified, monkeypatch):
    release = Event()
    slow_started = Event()
    def provider(self, source, query, page):
        if source == 'asura':
            slow_started.set()
            assert release.wait(5), 'Slow source was not released'
        return {'itens': [item(source, 'Shared title', source)], 'has_next': False}
    monkeypatch.setattr(UnifiedCatalog, 'provider', provider)
    response = unified.get('/api/catalog/stream', buffered=False)
    events = iter(response.response)
    try:
        assert json.loads(next(events))['started']
        first = json.loads(next(events))
        assert slow_started.wait(1)
        assert not release.is_set()
        assert not first['done'] and first['completed'] == 1
        assert 'Shared title' in first['html']
        release.set()
        final = json.loads(next(events))
        assert final['done']
        assert final['html'].count('class="manga-card"') == 1
        assert 'MangaDex · AsuraScans' in final['html']
        assert list(events) == []
    finally:
        release.set()
        response.close()


def test_completed_catalog_cache_avoids_provider_calls(unified, monkeypatch):
    first = unified.get('/api/catalog/stream?query=Shared').text
    def forbidden(*args):
        pytest.fail('Completed results should reuse the shared cache')
    monkeypatch.setattr(UnifiedCatalog, 'provider', forbidden)
    second = unified.get('/api/catalog/stream?query=Shared').text
    assert json.loads(first.splitlines()[-1])['html'] == json.loads(second.splitlines()[-1])['html']
    assert len(second.splitlines()) == 2


def test_stream_reports_failure_without_hiding_working_sources(unified, monkeypatch):
    def provider(self, source, query, page):
        if source == 'asura':
            raise SourceUnavailable('down')
        return {'itens': [item('md', 'Available title')], 'has_next': False}
    monkeypatch.setattr(UnifiedCatalog, 'provider', provider)
    response = unified.get('/api/catalog/stream')
    final = json.loads(response.text.splitlines()[-1])
    assert final['done'] and final['unavailable'] == ['AsuraScans']
    assert 'Available title' in final['html']
    assert response.headers['Content-Encoding'] == 'identity'


def test_stream_all_failed_has_retryable_error(unified, monkeypatch):
    def failed(*args):
        raise SourceUnavailable('down')
    monkeypatch.setattr(UnifiedCatalog, 'provider', failed)
    final = json.loads(unified.get('/api/catalog/stream').text.splitlines()[-1])
    assert final['done'] and 'unavailable' in final['error']


def test_simultaneous_readers_share_the_inflight_refresh(unified, context, monkeypatch):
    calls = []
    def provider(self, source, query, page):
        calls.append(source)
        return {'itens': [item(source, 'Shared title', source)], 'has_next': False}
    monkeypatch.setattr(UnifiedCatalog, 'provider', provider)
    catalog = UnifiedCatalog(Library())
    owner, follower = catalog.iter_listing(), catalog.iter_listing()
    try:
        first = next(owner)
        assert not first['done']
        assert next(follower) == {'waiting': True}
        assert next(follower)['completed'] == 1
        final = next(owner)
        assert final['done']
        shared = next(follower)
        assert shared['done'] and len(shared['itens']) == 1
        assert sorted(calls) == ['asura', 'mangadex']
    finally:
        owner.close()
        follower.close()


def test_shared_cache_separates_query_and_page(unified, context, monkeypatch):
    calls = []
    def provider(self, source, query, page):
        calls.append((source, query, page))
        return {'itens': [], 'has_next': False}
    monkeypatch.setattr(UnifiedCatalog, 'provider', provider)
    catalog = UnifiedCatalog(Library())
    catalog.listing('first', 1)
    catalog.listing('second', 1)
    catalog.listing('first', 2)
    catalog.listing('first', 1)
    assert len(calls) == 6
