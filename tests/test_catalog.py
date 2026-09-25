import pytest
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
    for path in ('/search?query=Shared', '/mangas'):
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
    result = unified.get('/search?query=test')
    assert result.status_code == 200
    assert 'Still available' in result.text
    assert 'Não foi possível consultar: AsuraScans' in result.text


def test_all_failures_report_unavailability(unified, monkeypatch):
    def fail(*args):
        raise SourceUnavailable('down')
    monkeypatch.setattr(UnifiedCatalog, 'provider', fail)
    assert unified.get('/mangas').status_code == 503


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
