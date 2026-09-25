"""Synthetic public-page fixtures; tests never request the upstream site."""
from urllib.parse import parse_qs, urlsplit

import pytest
import requests

from demonicscans.app import create_app
from demonicscans.client import BASE_URL, DemonicScans, SourceError, Transport, checked_url, remote_id, series_path

SLUG = 'Story-Max%25252DLevel'
IDENTIFIER = SLUG.encode().hex()
TAGS = '<li><input name="genres[]" value="33"> Isekai</li>'
CARD = f'<div class="advanced-element"><a href="/manga/{SLUG}" title="Story Max-Level"><img src="https://readermc.org/cover.jpg"><h1>Story...</h1></a></div>'
CATALOG = f'{TAGS}<div id="advanced-content">{CARD}</div><div class="pagination"><a href="/advanced.php?list=2">Next</a></div>'
SEARCH = f'<a href="/manga/{SLUG}"><img src="https://readermc.org/cover.jpg"><div class="seach-right"><div>Story Max-Level</div><div>100 views</div></div></a>'
SERIES = '''<meta property="og:image" content="https://readermc.org/cover.jpg">
<div id="manga-info-rightColumn"><h1>Story Max-Level</h1><div class="white-font">Description</div></div>
<div id="manga-info-stats"><div><li>Author</li><li>Writer</li></div><div><li>Status</li><li>Ongoing</li></div><div><li>Alternatives</li><li>Story;Other title;</li></div></div>
<ul class="genres-list"><li>Isekai</li></ul>
<div id="chapters-list"><a class="chplinks" href="/chaptered.php?manga=12&amp;chapter=2.5">Chapter 2.5</a><a class="chplinks" href="/chaptered.php?manga=12&amp;chapter=0">Chapter 0</a></div>'''
IMAGES = ['https://cdn.demoniclibs.com/Story/2.5/2.jpg', 'https://cdn.demoniclibs.com/Story/2.5/1.jpg']
READER = '<img src="https://readermc.org/avatar.jpg">' + ''.join(f'<img class="imgholder" src="{url}">' for url in IMAGES + IMAGES[:1]) + '<a href="/premium.php"><img class="imgholder" src="/img/free_ads.jpg"></a>'


class FakeTransport:
    def __init__(self):
        self.calls = []
        self.documents = {'/advanced.php': CATALOG, '/search.php': SEARCH,
                          '/manga/' + SLUG: SERIES, '/chaptered.php': READER}

    def get(self, url, *, image=False):
        self.calls.append(url)
        if image:
            return b'image-bytes', 'image/jpeg'
        parsed = urlsplit(url)
        return self.documents.get(parsed.path + '?' + parsed.query,
                                  self.documents[parsed.path]).encode(), 'text/html'


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError('Unexpected network call')
    monkeypatch.setattr(requests.sessions.Session, 'request', blocked)


@pytest.fixture
def service():
    return DemonicScans(FakeTransport())


def test_catalog_pagination_and_cache(service):
    data = service.listing()
    assert data['total'] is None and data['has_next'] is True
    assert data['results'][0]['title'] == 'Story Max-Level'
    assert data['results'][0]['id'] == IDENTIFIER
    data['results'].clear()
    assert service.listing()['results']
    assert len(service.transport.calls) == 1
    assert service.listing(2)['has_next'] is False


def test_search_paginates_and_encodes_query(service):
    assert service.listing(query='Story & Max')['total'] == 1
    assert service.listing(2, query='Story & Max')['results'] == []
    assert len(service.transport.calls) == 1
    assert parse_qs(urlsplit(service.transport.calls[0]).query)['manga'] == ['Story & Max']


def test_tag_and_combined_search(service):
    assert service.tags() == [{'id': '33', 'name': 'Isekai'}]
    assert service.listing(tag='33', query='Story')['results']
    assert parse_qs(urlsplit(service.transport.calls[1]).query)['genre[]'] == ['33']
    service.transport.documents['/search.php'] = ''
    assert service.listing(tag='33', query='missing')['results'] == []
    with pytest.raises(SourceError):
        service.listing(tag='invalid')


def test_metadata_chapters_and_encoding(service):
    assert series_path(IDENTIFIER) == '/manga/' + SLUG
    assert remote_id('/manga/' + SLUG) == IDENTIFIER
    assert series_path(remote_id('/manga/Who%253F')) == '/manga/Who%253F'
    data = service.info(IDENTIFIER)
    assert data['authors'] == ['Writer'] and data['aliases'] == ['Story', 'Other title']
    assert data['tagLinks'] == [{'id': '33', 'name': 'Isekai'}]
    assert '_chapters' not in data
    assert [item['number'] for item in service.chapters(IDENTIFIER)['chapters']] == ['2.5', '0']


def test_reader_order_deduplication_and_ads(service):
    assert service.pages(IDENTIFIER, '12-2.5')['pages'] == IMAGES
    assert service.pages(IDENTIFIER, '12-2.5')['pages'] == IMAGES
    assert len(service.transport.calls) == 2
    with pytest.raises(SourceError, match='pertence'):
        service.pages(IDENTIFIER, '13-2.5')
    assert len(service.transport.calls) == 2


@pytest.mark.parametrize('identifier', ['invalid', 'abc', 'ff', '', '2e2e', '2f2f6576696c'])
def test_invalid_series_identifiers(identifier):
    with pytest.raises(SourceError):
        series_path(identifier)


def test_empty_search_is_distinct_from_challenge(service):
    service.transport.documents['/search.php'] = ''
    assert service.listing(query='missing')['total'] == 0
    service.transport.documents['/search.php'] = '<html><title>Just a moment</title></html>'
    with pytest.raises(SourceError):
        service.listing(query='blocked')


@pytest.mark.parametrize('method,args,path', [('listing', (), '/advanced.php'),
    ('info', (IDENTIFIER,), '/manga/' + SLUG),
    ('pages', (IDENTIFIER, '12-2.5'), '/chaptered.php')])
def test_changed_or_blocked_markup_fails(service, method, args, path):
    service.transport.documents[path] = '<html>Unavailable</html>'
    with pytest.raises(SourceError):
        getattr(service, method)(*args)


def test_api_contract(service):
    client = create_app(service).test_client()
    for path in ['/api/health', '/api/manga/catalog', '/api/manga/search?q=Story', '/api/manga/tags',
                 '/api/manga/' + IDENTIFIER, '/api/manga/' + IDENTIFIER + '/chapters',
                 '/api/manga/' + IDENTIFIER + '/chapters/12-2.5/pages']:
        response = client.get(path)
        assert response.status_code == 200, response.json
        assert response.json['source'] == 'demonicscans'
    for suffix in ['page=0', 'page=501', 'page=bad', 'source=asura', 'q=' + 'x' * 121]:
        assert client.get('/api/manga/catalog?' + suffix).status_code == 400
    assert client.get('/api/proxy/image?url=http://localhost').status_code == 400
    assert client.get('/api/proxy/image?url=https://readermc.org/cover.jpg').content_type == 'image/jpeg'


@pytest.mark.parametrize('url', ['http://cdn.demoniclibs.com/a.jpg', 'https://cdn.demoniclibs.com.evil.example/a',
                              'https://localhost/a', 'https://127.0.0.1/a',
                              'https://user:password@cdn.demoniclibs.com/a', 'https://cdn.demoniclibs.com:8080/a',
                              '//cdn.demoniclibs.com/a', 'file:///etc/passwd'])
def test_proxy_url_validation(url):
    with pytest.raises(SourceError):
        checked_url(url, image=True)


class FakeResponse:
    def __init__(self, status=200, headers=None, body=b'<html></html>'):
        self.status_code = status
        self.headers = headers or {'Content-Type': 'text/html'}
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def iter_content(self, size):
        yield self.body


def test_redirect_to_cdn_and_content_type(monkeypatch):
    responses = iter([FakeResponse(302, {'Location': 'https://cdn.demoniclibs.com/a.jpg'}),
                      FakeResponse(headers={'Content-Type': 'image/jpeg'}, body=b'jpeg')])
    monkeypatch.setattr(requests, 'get', lambda *a, **kw: next(responses))
    assert Transport().get('https://readermc.org/a.jpg', image=True) == (b'jpeg', 'image/jpeg')


def test_redirect_cannot_reach_internal_host(monkeypatch):
    calls = []
    def get(url, **kwargs):
        calls.append(url)
        return FakeResponse(302, {'Location': 'http://127.0.0.1/secret'})
    monkeypatch.setattr(requests, 'get', get)
    with pytest.raises(SourceError):
        Transport().get('https://cdn.demoniclibs.com/a.jpg', image=True)
    assert len(calls) == 1


def test_429_sets_cooldown_and_api_retry_header(service, monkeypatch):
    calls = []
    def get(*args, **kwargs):
        calls.append(1)
        return FakeResponse(429, {'Retry-After': '120'})
    monkeypatch.setattr(requests, 'get', get)
    service.transport = Transport()
    client = create_app(service).test_client()
    first = client.get('/api/manga/catalog')
    second = client.get('/api/manga/search?q=another')
    assert first.status_code == second.status_code == 503
    assert first.headers['Retry-After'] == '120'
    assert len(calls) == 1


def test_html_is_not_served_as_an_image(monkeypatch):
    monkeypatch.setattr(requests, 'get', lambda *a, **kw: FakeResponse())
    with pytest.raises(SourceError, match='Tipo'):
        Transport().get('https://cdn.demoniclibs.com/a.jpg', image=True)


def test_bounded_download(monkeypatch):
    monkeypatch.setattr(requests, 'get', lambda *a, **kw: FakeResponse(body=b'x' * (4 * 1024 * 1024 + 1)))
    with pytest.raises(SourceError, match='tamanho'):
        Transport().get(BASE_URL)


