from copy import deepcopy
from urllib.parse import parse_qs, urlsplit

import pytest
import requests

from app import cache, db
from app.libs.library import Library
from app.libs.manga_novel import MangaNovel, SourceUnavailable
from app.models import Favorite, Readed, SourceReference, User


@pytest.fixture
def qiscans_api(app, monkeypatch):
    app.config['QISCANS_API_URL'] = 'http://qiscans:3002'
    calls = []

    def get(url, params=None, timeout=None):
        calls.append((url, params))
        assert url.startswith('http://qiscans:3002/')
        path = urlsplit(url).path
        if path.endswith('/health'):
            data = {'status': 'ok'}
        elif path.endswith('/tags'):
            data = {'tags': [{'id': '3', 'name': 'Action'}]}
        elif path.endswith('/search') or path.endswith('/catalog'):
            assert params['source'] == 'qiscans'
            data = {'results': [{'id': 'story', 'title': 'Qi Story',
                                 'coverUrl': 'https://i0.wp.com/cover.jpg'}],
                    'total': None, 'has_next': params['page'] == 1}
        elif path.endswith('/pages'):
            data = {'pages': ['https://i0.wp.com/i.imgur.com/page.jpg']}
        elif path.endswith('/chapters'):
            data = {'chapters': [{'id': 'story-chapter-' + n, 'number': n, 'lang': 'en'}
                                 for n in ['2.5', '1']], 'total': 2}
        else:
            data = {'title': 'Qi Story', 'description': 'Description', 'authors': ['Author'],
                    'genres': ['Action'], 'tagLinks': [{'id': '3', 'name': 'Action'}]}
        response = requests.Response()
        response.status_code = 200
        response.json = lambda: {'source': 'qiscans', **deepcopy(data)}
        return response

    monkeypatch.setattr(requests, 'get', get)
    return calls


def test_qiscans_configuration_is_independent(app, qiscans_api):
    with app.test_request_context():
        assert Library.sources() == {'mangadex': 'MangaDex', 'qiscans': 'Qi Scans'}
        assert MangaNovel('qiscans').base == 'http://qiscans:3002'
        app.config['QISCANS_API_URL'] = ''
        app.config['MANGA_NOVEL_API_URL'] = 'http://source-api:3001'
        assert 'qiscans' not in Library.sources()
        with pytest.raises(SourceUnavailable):
            MangaNovel('qiscans')
    assert app.test_client().get('/mangas?source=qiscans').status_code == 400


@pytest.mark.parametrize('route', ['/mangas', '/search?query=story'])
def test_qiscans_honors_next_page_even_with_less_than_20_results(app, qiscans_api, route):
    client = app.test_client()
    separator = '&' if '?' in route else '?'
    result = client.get(route + separator + 'source=qiscans')
    assert result.status_code == 200
    assert 'Qi Story' in result.text and '/2?' in result.text
    path, _, query = route.partition('?')
    second = client.get(path + '/2?source=qiscans&' + query)
    assert second.status_code == 200
    assert path + '/3?' not in second.text
    assert qiscans_api[-1][1]['page'] == 2


def test_qiscans_genres_work_in_tags_details_and_search(app, qiscans_api):
    client = app.test_client()
    assert 'Action' in client.get('/tags?source=qiscans').text
    result = client.get('/search?source=qiscans&query=story&tag=3')
    assert result.status_code == 200
    assert qiscans_api[-1][1]['tag'] == '3' and qiscans_api[-1][1]['q'] == 'story'
    with app.test_request_context():
        identifier = MangaNovel('qiscans').search('story')['itens'][0]['id']
    assert 'source=qiscans&amp;tag=3' in client.get('/manga/' + identifier).text


def test_qiscans_reading_favorites_history_and_cache(app, qiscans_api):
    with app.test_request_context():
        user = User(username='qi-reader', email='qi@example.com', password_hash='unused')
        db.session.add(user)
        db.session.commit()
        user_id = user.id
        service = MangaNovel('qiscans')
        identifier = service.search('story')['itens'][0]['id']
        before = len(qiscans_api)
        assert service.search('story')['itens'][0]['id'] == identifier
        assert len(qiscans_api) == before
        cache.clear()
        assert service.search('story')['itens'][0]['id'] == identifier
        info = Library().showManga(identifier)
        first_id = info['first_chapter']
        assert info['chapters'][0]['cap'] == '2.5'
        first = Library().getChapter(first_id)
        assert first['prev'] is None and first['next'] == info['chapters'][0]['cap_id']
        nested = parse_qs(urlsplit(first['pages'][0]).query)['url'][0]
        assert nested.startswith('http://qiscans:3002/api/proxy/image?')
        assert SourceReference.query.filter_by(kind='manga', source='qiscans').count() == 1
    client = app.test_client()
    with client.session_transaction() as session:
        session['_user_id'] = str(user_id)
        session['_fresh'] = True
    assert client.get(f'/manga/{identifier}/favorite').status_code == 200
    assert client.get(f'/cap/{first_id}/readed').status_code == 200
    with app.app_context():
        assert Favorite.query.count() == Readed.query.count() == 1


def test_qiscans_failure_uses_existing_unavailable_page(app, qiscans_api, monkeypatch):
    def unavailable(*args, **kwargs):
        raise requests.Timeout()
    monkeypatch.setattr(requests, 'get', unavailable)
    result = app.test_client().get('/mangas?source=qiscans')
    assert result.status_code == 503
    assert 'Buscar em MangaDex' in result.text


def test_qiscans_health_is_visible(app, qiscans_api):
    result = app.test_client().get('/status')
    assert result.status_code == 200
    assert 'Qi Scans' in result.text
    assert any(url.endswith('/api/health') for url, _ in qiscans_api)
