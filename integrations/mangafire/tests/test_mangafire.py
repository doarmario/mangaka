from copy import deepcopy
import json
from urllib.parse import parse_qs, urlsplit

import pytest
import requests

from mangafire.app import create_app
from mangafire.client import MangaFire, SourceError, Transport, checked_url, identifier
from mangafire.signature import signed_path


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError('Unexpected network request')
    monkeypatch.setattr(requests, 'get', blocked)


class FakeTransport:
    def __init__(self):
        self.calls = []
        self.responses = {}

    def get(self, url, **kwargs):
        self.calls.append(url)
        path = urlsplit(url).path.removeprefix('/api')
        value = self.responses[path]
        if callable(value):
            value = value(parse_qs(urlsplit(url).query))
        return json.dumps(deepcopy(value)).encode(), 'application/json'


@pytest.fixture
def service():
    transport = FakeTransport()
    record = {'hid': 'abc', 'title': 'Example', 'poster': {'large': 'https://static.mfcdn.nl/cover.jpg'},
              'type': 'manga', 'status': 'finished', 'altTitles': ['別名', 'Outro título'],
              'synopsisHtml': '<p>A <b>story</b>.</p>', 'authors': [{'title': 'Author'}],
              'artists': [{'title': 'Artist'}], 'year': 2020, 'malId': '123', 'anilistId': '456',
              'genres': [{'id': 1, 'title': 'Action'}], 'themes': [{'id': 2, 'title': 'Isekai'}],
              'links': {'md': 'https://mangadex.org/title/b1ca3c5a-03f1-470f-b210-e92a60492fe5/'}}
    transport.responses = {
        '/titles': {'items': [record], 'meta': {'total': 21, 'hasNext': True}},
        '/titles/abc': {'data': record},
        '/filter-options': {'data': {'genres': [{'id': 1, 'name': 'Action'}],
                                    'themes': [{'id': 2, 'name': 'Isekai'}]}},
        '/titles/abc/chapters': lambda p: {'items': [
            {'id': 11, 'number': '12.5', 'name': 'Bonus', 'language': p['language'][0]},
            {'id': 12, 'number': 'Prologue', 'language': p['language'][0]}],
            'meta': {'total': 2, 'hasNext': False}},
        '/chapters/11': {'data': {'id': 11, 'title': {'hid': 'abc'}, 'language': 'en',
                                  'pages': [{'url': 'https://m3z.mfcdn3.xyz/chapter/page.jpg'}]}},
    }
    return MangaFire(transport)


def test_signature_recorded_vectors_and_canonical_query_order():
    expected = '/api/titles?limit=20&page=1&vrf=8sK3xtqdFZdD1d-yEmmIZ2aMrJChBws'
    assert signed_path('/titles', [('page', '1'), ('limit', '20')]) == expected
    assert signed_path('/titles', [('limit', '20'), ('page', '1')]) == expected
    assert signed_path('/chapters/156') == '/api/chapters/156?vrf=8vPRXa1JjvVTxq_QNA'
    assert signed_path('/titles', [('keyword', 'Solo Leveling'), ('page', '1'), ('limit', '20')]).endswith(
        'vrf=8sK3xtqdFZfetBhus6bRAuzLtZTk514b9Flx2njo6aaQt7_fOVE4uRPGkCI9')


def test_catalog_search_tags_metadata_and_pages(service):
    client = create_app(service).test_client()
    assert client.get('/api/health').json == {'source': 'mangafire', 'status': 'ok'}
    data = client.get('/api/manga/catalog?page=1&tag=theme:2&q=Example').json
    assert data['source'] == 'mangafire'
    assert data['results'][0]['id'] == 'abc'
    assert data['total_pages'] == 2 and data['has_next']
    params = parse_qs(urlsplit(service.transport.calls[-1]).query)
    assert params['theme_ids[0]'] == ['2'] and params['keyword'] == ['Example']
    assert client.get('/api/manga/search?q=Example').status_code == 200
    assert client.get('/api/manga/tags').json['tags'][1] == {'id': 'theme:2', 'name': 'Isekai'}
    info = client.get('/api/manga/abc').json
    assert info['aliases'] == ['別名', 'Outro título']
    assert info['status'] == 'completed' and info['authors'] == ['Author']
    assert '<' not in info['description']
    assert info['external_ids']['mangadex'] == 'b1ca3c5a-03f1-470f-b210-e92a60492fe5'
    for lang in ('en', 'pt-br'):
        data = client.get('/api/manga/abc/chapters?lang=' + lang).json
        assert [x['number'] for x in data['chapters']] == ['12.5', 'Prologue']
        assert all(x['lang'] == lang for x in data['chapters'])
    assert client.get('/api/manga/abc/chapters/11/pages').json['pages'] == ['https://m3z.mfcdn3.xyz/chapter/page.jpg']
    assert client.get('/api/manga/other/chapters/11/pages').status_code == 404


def test_cache_is_bounded_and_returns_copies(service):
    first = service.info('abc')
    first['title'] = 'Changed'
    assert service.info('abc')['title'] == 'Example'
    assert len(service.transport.calls) == 1
    for page in range(1, 135):
        service.listing(page)
    assert len(service.cache) == 128


@pytest.mark.parametrize('path', [
    '/api/manga/catalog?page=0', '/api/manga/catalog?page=no',
    '/api/manga/catalog?page=10001', '/api/manga/catalog?tag=genre:../../x',
    '/api/manga/catalog?source=asura', '/api/manga/catalog?q=' + 'x' * 121,
    '/api/manga/abc/chapters?lang=ja', '/api/manga/abc/chapters?page=101',
    '/api/manga/abc/chapters/not-numeric/pages',
    '/api/proxy/image?url=http://127.0.0.1/private',
])
def test_invalid_input_does_not_reach_upstream(service, path):
    assert create_app(service).test_client().get(path).status_code == 400
    assert not service.transport.calls


@pytest.mark.parametrize('url', [
    'http://static.mfcdn.nl/a', 'https://mfcdn.nl.evil.test/a',
    'https://m3z.mfcdn3.xyz.evil.test/a', 'https://127.0.0.1/a',
    'https://user:password@static.mfcdn.nl/a', 'https://static.mfcdn.nl:444/a',
    'file:///etc/passwd', 'https://mangafire.to/a', '', None,
])
def test_image_proxy_restricts_hosts(url):
    with pytest.raises(SourceError):
        checked_url(url, image=True)


def test_image_proxy_accepts_legacy_jpg_mime(monkeypatch):
    class Response:
        status_code = 200
        headers = {'Content-Type': 'image/jpg', 'Content-Length': '4'}
        content = b'\xff\xd8\xff\xd9'

        def raise_for_status(self):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def iter_content(self, _chunk_size):
            yield self.content

    monkeypatch.setattr('requests.get', lambda *args, **kwargs: Response())
    body, content_type = Transport().get('https://static.mfcdn.nl/cover.jpg', image=True)
    assert body == b'\xff\xd8\xff\xd9'
    assert content_type == 'image/jpg'


@pytest.mark.parametrize('value', ['../x', 'abc/def', 'a?b', '%2f', '', 'x' * 65])
def test_ids_cannot_escape_api_path(value):
    with pytest.raises(SourceError):
        identifier(value)


def test_redirect_to_private_address_is_rejected(monkeypatch):
    calls = []
    class Reply:
        status_code = 302
        headers = {'Location': 'http://127.0.0.1/private'}
        def __enter__(self): return self
        def __exit__(self, *args): pass
    def get(url, **kwargs):
        calls.append(url)
        return Reply()
    monkeypatch.setattr(requests, 'get', get)
    with pytest.raises(SourceError):
        Transport().get('https://static.mfcdn.nl/a', image=True)
    assert len(calls) == 1


def test_rate_limit_cooldown_and_retry_after(monkeypatch):
    calls = []
    class Reply:
        status_code = 429
        headers = {'Retry-After': '60'}
        def __enter__(self): return self
        def __exit__(self, *args): pass
    def get(url, **kwargs):
        calls.append(url)
        return Reply()
    monkeypatch.setattr(requests, 'get', get)
    transport = Transport()
    for _ in range(2):
        with pytest.raises(SourceError) as error:
            transport.get('https://mangafire.to/api/titles')
        assert error.value.status == 503 and error.value.retry_after
    assert len(calls) == 1


def test_bad_pagination_is_not_an_empty_success(service):
    service.transport.responses['/titles']['meta'] = {}
    assert create_app(service).test_client().get('/api/manga/catalog').status_code == 502


def test_portuguese_chapter_cdn_is_supported(service):
    service.transport.responses['/chapters/11']['data']['language'] = 'pt-br'
    service.transport.responses['/chapters/11']['data']['pages'] = [
        {'url': 'https://o48.mfcdn2.xyz/chapter/page.jpg'}]
    assert service.pages('abc', '11')['pages'] == ['https://o48.mfcdn2.xyz/chapter/page.jpg']
    with pytest.raises(SourceError):
        checked_url('https://o48.mfcdn2.xyz.evil.test/chapter/page.jpg', image=True)
