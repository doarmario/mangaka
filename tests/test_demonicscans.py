from copy import deepcopy
from urllib.parse import parse_qs, urlsplit

import pytest
import requests

from app import cache, db
from app.libs.library import Library
from app.libs.manga_novel import MangaNovel, SourceUnavailable
from app.models import Favorite, Readed, SourceReference, User


@pytest.fixture
def demonicscans_api(app, monkeypatch):
    app.config['DEMONICSCANS_API_URL'] = 'http://demonicscans:3003'
    calls = []

    def get(url, params=None, timeout=None):
        calls.append((url, params))
        assert url.startswith('http://demonicscans:3003/')
        path = urlsplit(url).path
        if path.endswith('/health'):
            data = {'status': 'ok'}
        elif path.endswith('/tags'):
            data = {'tags': [{'id': '3', 'name': 'Action'}]}
        elif path.endswith('/search') or path.endswith('/catalog'):
            assert params['source'] == 'demonicscans'
            data = {'results': [{'id': 'story', 'title': 'Demonic Story',
                                 'coverUrl': 'https://readermc.org/cover.jpg'}],
                    'total': None, 'total_pages': None, 'page_size': 56,
                    'page': min(params['page'], 2), 'has_next': params['page'] == 1}
        elif path.endswith('/pages'):
            data = {'pages': ['https://cdn.demoniclibs.com/page.jpg']}
        elif path.endswith('/chapters'):
            data = {'chapters': [{'id': 'story-chapter-' + n, 'number': n, 'lang': 'en'}
                                 for n in ['2.5', '1']], 'total': 2}
        else:
            data = {'title': 'Demonic Story', 'description': 'Description', 'authors': ['Author'],
                    'genres': ['Action'], 'tagLinks': [{'id': '3', 'name': 'Action'}]}
        response = requests.Response()
        response.status_code = 200
        response.json = lambda: {'source': 'demonicscans', **deepcopy(data)}
        return response

    monkeypatch.setattr(requests, 'get', get)
    return calls


def test_demonicscans_configuration_is_independent(app, demonicscans_api):
    with app.test_request_context():
        assert Library.sources() == {'mangadex': 'MangaDex', 'demonicscans': 'Demonic Scans'}
        assert MangaNovel('demonicscans').base == 'http://demonicscans:3003'
        app.config['DEMONICSCANS_API_URL'] = ''
        app.config['MANGA_NOVEL_API_URL'] = 'http://source-api:3001'
        assert 'demonicscans' not in Library.sources()
        with pytest.raises(SourceUnavailable):
            MangaNovel('demonicscans')
    assert app.test_client().get('/mangas?source=demonicscans').status_code == 400


@pytest.mark.parametrize('route', ['/mangas', '/search?query=story'])
def test_demonicscans_uses_upstream_pagination(app, demonicscans_api, route):
    client = app.test_client()
    separator = '&' if '?' in route else '?'
    result = client.get(route + separator + 'source=demonicscans')
    assert result.status_code == 200
    assert 'Demonic Story' in result.text and '/2?' in result.text
    path, _, query = route.partition('?')
    second = client.get(path + '/2?source=demonicscans&' + query)
    assert second.status_code == 200
    assert path + '/3?' not in second.text
    assert demonicscans_api[-1][1]['page'] == 2


def test_demonicscans_genres_work_in_tags_details_and_search(app, demonicscans_api):
    client = app.test_client()
    assert 'Action' in client.get('/tags?source=demonicscans').text
    result = client.get('/search?source=demonicscans&query=story&tag=3')
    assert result.status_code == 200
    assert demonicscans_api[-1][1]['tag'] == '3' and demonicscans_api[-1][1]['q'] == 'story'
    with app.test_request_context():
        identifier = MangaNovel('demonicscans').search('story')['itens'][0]['id']
    assert 'source=demonicscans&amp;tag=3' in client.get('/manga/' + identifier).text


def test_demonicscans_reading_favorites_history_and_cache(app, demonicscans_api):
    with app.test_request_context():
        user = User(username='qi-reader', email='qi@example.com', password_hash='unused')
        db.session.add(user)
        db.session.commit()
        user_id = user.id
        service = MangaNovel('demonicscans')
        identifier = service.search('story')['itens'][0]['id']
        before = len(demonicscans_api)
        assert service.search('story')['itens'][0]['id'] == identifier
        assert len(demonicscans_api) == before
        cache.clear()
        assert service.search('story')['itens'][0]['id'] == identifier
        info = Library().showManga(identifier)
        first_id = info['first_chapter']
        assert info['chapters'][0]['cap'] == '2.5'
        first = Library().getChapter(first_id)
        assert first['prev'] is None and first['next'] == info['chapters'][0]['cap_id']
        nested = parse_qs(urlsplit(first['pages'][0]).query)['url'][0]
        assert nested.startswith('http://demonicscans:3003/api/proxy/image?')
        assert SourceReference.query.filter_by(kind='manga', source='demonicscans').count() == 1
    client = app.test_client()
    with client.session_transaction() as session:
        session['_user_id'] = str(user_id)
        session['_fresh'] = True
    assert client.get(f'/manga/{identifier}/favorite').status_code == 200
    assert client.get(f'/cap/{first_id}/readed').status_code == 200
    with app.app_context():
        assert Favorite.query.count() == Readed.query.count() == 1


def test_demonicscans_failure_uses_existing_unavailable_page(app, demonicscans_api, monkeypatch):
    def unavailable(*args, **kwargs):
        raise requests.Timeout()
    monkeypatch.setattr(requests, 'get', unavailable)
    result = app.test_client().get('/mangas?source=demonicscans')
    assert result.status_code == 503
    assert 'Buscar em MangaDex' in result.text


def test_demonicscans_health_is_visible(app, demonicscans_api):
    result = app.test_client().get('/status')
    assert result.status_code == 200
    assert 'Demonic Scans' in result.text
    assert any(url.endswith('/api/health') for url, _ in demonicscans_api)


def test_demonicscans_participates_in_cross_source_search(app, demonicscans_api, monkeypatch):
    from app.libs.catalog import UnifiedCatalog
    monkeypatch.setattr(Library, 'searchMangaByTitle', lambda *args: {
        'itens': [{'id': 'md-story', 'title': 'Demonic Story'}], 'total': 1})
    with app.test_request_context():
        result = UnifiedCatalog(Library()).listing(query='story')
        assert len(result['itens']) == 1
        assert {item['source_id'] for item in result['itens'][0]['sources']} == {'mangadex', 'demonicscans'}
        assert result['unavailable'] == []
