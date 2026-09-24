from copy import deepcopy
from urllib.parse import unquote, urlsplit, parse_qs
import pytest
import requests
from flask_login import login_user

from app import cache, db
from app.libs.library import Library
from app.libs.manga_novel import MangaNovel, SourceUnavailable, register_many
from app.models import SourceReference, User


@pytest.fixture
def source_api(app, monkeypatch):
    app.config['MANGA_NOVEL_API_URL'] = 'http://source-api:3001'
    calls = []
    def get(url, params, timeout):
        calls.append((url, params))
        source = params['source']
        path = unquote(urlsplit(url).path)
        if path.endswith('/search'):
            data = {'results': [{'id': 'series/123/title', 'title': 'Story', 'coverUrl': 'https://cdn.example/cover.jpg'}]}
        elif path.endswith('/pages'):
            data = {'pages': ['https://cdn.example/page.jpg?a=1&b=2']}
        elif path.endswith('/chapters'):
            data = {'chapters': [{'id': f'chapters/{n}', 'number': str(n), 'lang': 'en'} for n in (1, 2)], 'total': None}
        else:
            data = {'title': 'Story', 'description': 'Description', 'genres': [], 'authors': ['Author']}
        response = requests.Response()
        response.status_code = 200
        response.json = lambda: {'source': source, **deepcopy(data)}
        return response
    monkeypatch.setattr(requests, 'get', get)
    return calls


def test_provider_ids_do_not_collide_and_survive_cache_clear(context, source_api):
    first = MangaNovel('weebcentral').search('story')['itens'][0]['id']
    second = MangaNovel('asura').search('story')['itens'][0]['id']
    assert first != second
    assert len(first) == len(second) == 36
    cache.clear()
    assert MangaNovel('weebcentral').search('story')['itens'][0]['id'] == first
    assert SourceReference.query.filter_by(kind='manga').count() == 2


def test_source_reading_uses_correct_parent_language_and_proxy(context, source_api):
    manga_id = MangaNovel('weebcentral').search('story')['itens'][0]['id']
    library = Library()
    details = library.showManga(manga_id)
    assert details['source_name'] == 'WeebCentral'
    assert details['languages'] == [{'code': 'en', 'name': 'English'}]
    result = library.getChapter(details['first_chapter'])
    assert result['manga_id'] == manga_id
    assert result['prev'] is None
    assert result['next'] == details['chapters'][0]['cap_id']
    assert result['language'] == 'en'
    assert '%2F' in source_api[-1][0]
    proxy = parse_qs(urlsplit(result['pages'][0]).query)['url'][0]
    assert parse_qs(urlsplit(proxy).query)['url'] == ['https://cdn.example/page.jpg?a=1&b=2']
    assert library.id2Cover(manga_id, size='256').endswith('cover.jpg')
    assert not library.id2Cover(manga_id, size='256').endswith('.256.jpg')


def test_cache_avoids_repeating_source_queries(context, source_api):
    service = MangaNovel('weebcentral')
    service.search('story')
    service.search('story')
    assert len(source_api) == 1


def test_wrong_source_response_is_rejected_and_cooled_down(context, source_api, monkeypatch):
    calls = []
    def wrong(*args, **kwargs):
        calls.append(1)
        response = requests.Response()
        response.status_code = 200
        response.json = lambda: {'source': 'mangadex', 'results': []}
        return response
    monkeypatch.setattr(requests, 'get', wrong)
    for query in ['one', 'two']:
        with pytest.raises(SourceUnavailable):
            MangaNovel('weebcentral').search(query)
    assert len(calls) == 1


def test_source_search_keeps_provider_in_links_and_has_no_fake_total(app, source_api):
    response = app.test_client().get('/search?query=story&source=weebcentral')
    assert response.status_code == 200
    assert 'WeebCentral' in response.text
    assert 'name="source" value="weebcentral"' in response.text
    assert 'None' not in response.text


def test_source_error_renders_alternative_sources(app, source_api, monkeypatch):
    monkeypatch.setattr(requests, 'get', lambda *args, **kwargs: (_ for _ in ()).throw(requests.Timeout()))
    response = app.test_client().get('/search?query=story&source=weebcentral')
    assert response.status_code == 503
    assert 'Buscar em MangaDex' in response.text


def test_external_favorites_and_history_use_local_ids(app, source_api):
    from app.models import Favorite, Manga, Readed
    with app.app_context():
        user = User(username='reader', email='reader@example.com', password_hash='unused')
        db.session.add(user)
        db.session.commit()
        user_id = user.id
        manga_id = MangaNovel('weebcentral').search('story')['itens'][0]['id']
    client = app.test_client()
    with client.session_transaction() as session:
        session['_user_id'] = str(user_id)
        session['_fresh'] = True
    result = client.get(f'/manga/{manga_id}/favorite')
    assert result.status_code == 200
    with app.test_request_context():
        chapter_id = Library().showManga(manga_id)['first_chapter']
    assert client.get(f'/cap/{chapter_id}/readed').status_code == 200
    with app.app_context():
        assert Manga.query.one().uuid == manga_id
        assert Favorite.query.count() == 1
        assert Readed.query.count() == 1


def test_catalog_loads_titles_without_search_and_keeps_source_on_next_page(app, source_api, monkeypatch):
    calls = []
    def get(url, params, timeout):
        calls.append(params['page'])
        assert url.endswith('/api/manga/catalog')
        response = requests.Response()
        response.status_code = 200
        response.json = lambda: {'source': 'asura', 'results': [
            {'slug': 'comics/page-' + str(params['page']), 'title': 'Story ' + str(params['page'])}],
            'total': 41, 'has_next': params['page'] < 3}
        return response
    monkeypatch.setattr(requests, 'get', get)
    client = app.test_client()
    first = client.get('/mangas?source=asura')
    second = client.get('/mangas/2?source=asura')
    assert first.status_code == second.status_code == 200
    assert 'Story 1' in first.text
    assert 'Story 2' in second.text
    assert '/mangas/2?source=asura' in first.text
    assert '/mangas/3?source=asura' in second.text
    assert 'Busque uma história nesta fonte' not in first.text
    client.get('/mangas?source=asura')
    assert calls == [1, 2]


def test_catalog_reports_source_failure_instead_of_empty_success(app, source_api, monkeypatch):
    def unavailable(*args, **kwargs):
        raise requests.Timeout()
    monkeypatch.setattr(requests, 'get', unavailable)
    response = app.test_client().get('/mangas?source=comick')
    assert response.status_code == 503
    assert 'Esta fonte não respondeu.' in response.text
    assert 'Buscar em MangaDex' in response.text
