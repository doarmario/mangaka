"""Small synthetic fixtures based on the inspected MangaReader markup."""
import json
from urllib.parse import parse_qs, urlsplit

import pytest
import requests

from thunderscans.app import create_app
from thunderscans.client import BASE_URL, ThunderScans, SourceError, Transport, checked_url


TAGS = '''<input name="genre[]" id="genre-3" value="3"><label for="genre-3">Action</label>
<input name="genre[]" id="genre-4" value="4"><label for="genre-4">Sports</label>'''
CARD = '''<div class="bsx"><a href="/comics/story/"><div class="tt">Story &amp; Friends</div>
<img src="https://en-thunderscans.com/cover.jpg"></a></div>'''
CATALOG = f'''{TAGS}<div class="postbody"><div class="listupd">{CARD}
<div class="bsx"><span class="novelabel">Novel</span></div></div>
</div>
<aside><div class="listupd"><div class="bsx">Not a result</div></div></aside>'''
SERIES = '''<h1 class="entry-title">Story &amp; Friends</h1>
<div class="main-info"><div class="thumb"><img src="https://en-thunderscans.com/cover.jpg"></div></div>
<div class="tsinfo"><div class="imptdt">Author <i>Example Author</i></div>
<div class="imptdt">Released <i>2024</i></div><div class="imptdt">Status <i>Ongoing</i></div>
<div class="imptdt">Type <a>Manga</a></div></div>
<div class="entry-content" itemprop="description"><p>First paragraph.</p><p>Second paragraph.</p></div>
<div class="mgen"><a href="/genres/action/">Action</a></div>
<ul id="chapterlist">
<li data-num="2.5"><a href="/story-chapter-2-5/"><div class="chbox"><div class="eph-num"><span class="chapternum">Chapter 2.5</span></div></div></a></li>
<li data-num="1"><div class="eph-num"><a href="/story-chapter-1/"><span class="chapternum">Chapter 1</span></a></div></li>
<li class="locked" data-num="3"><div class="eph-num"><a href="/story-chapter-3/">Chapter 3</a></div></li>
<li data-num="4"><a href="#" data-bs-target="#lockedChapterModal">Chapter 4</a></li>
</ul>'''
IMAGES = ['https://en-thunderscans.com/second.jpg', 'https://en-thunderscans.com/first.jpg']


def reader(**overrides):
    data = dict(protected=False, is_novel=False, defaultSource="Server 2", sources=[
        {"source": "Server 1", "images": ["https://en-thunderscans.com/unused.jpg"]},
        {"source": "Server 2", "images": IMAGES}])
    data.update(overrides)
    return ('<div class="allc"><a href="/comics/story/">All chapters</a></div>'
            '<div id="readerarea"></div><script>ts_reader.run(' + json.dumps(data) + ');</script>')


class FakeTransport:
    def __init__(self):
        self.calls = []
        self.documents = {"/comics/": CATALOG, "/": CATALOG, "/page/2/": CATALOG,
                          "/comics/story/": SERIES, "/story-chapter-2-5/": reader()}

    def get(self, url, *, image=False):
        self.calls.append(url)
        if image:
            return b"image-bytes", "image/jpeg"
        parsed = urlsplit(url)
        if parse_qs(parsed.query).get('genre[]') == ['4']:
            return b'<div class="postbody"><div class="listupd">Not Found</div></div>', 'text/html'
        key = parsed.path + '?' + parsed.query
        return self.documents.get(key, self.documents.get(parsed.path, '')).encode(), "text/html"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("Unexpected network call")
    monkeypatch.setattr(requests.sessions.Session, "request", blocked)


@pytest.fixture
def service():
    return ThunderScans(FakeTransport())


def test_series_metadata_fractional_numbers_and_locked_chapters(service):
    data = service.info('story')
    assert data['year'] == 2024 and data['authors'] == ['Example Author']
    assert data['description'] == 'First paragraph. Second paragraph.'
    assert data['tagLinks'] == [{'id': '3', 'name': 'Action'}]
    chapters = service.chapters('story')['chapters']
    assert [c['number'] for c in chapters] == ['2.5', '1']
    assert all(c['lang'] == 'en' for c in chapters)
    assert sum('/comics/story/' in u for u in service.transport.calls) == 1


def test_reader_uses_selected_server_and_preserves_page_order(service):
    assert service.pages('story', 'story-chapter-2-5')['pages'] == IMAGES


def test_chapter_must_belong_to_series(service):
    with pytest.raises(SourceError) as exc:
        service.pages('story', 'other-chapter')
    assert exc.value.status == 404
    assert not any('/other-chapter/' in u for u in service.transport.calls)


def test_reader_parent_is_checked(service):
    service.transport.documents['/story-chapter-2-5/'] = reader().replace('/comics/story/', '/comics/other/')
    with pytest.raises(SourceError, match='outra obra'):
        service.pages('story', 'story-chapter-2-5')


@pytest.mark.parametrize('values', [dict(protected=True), dict(is_novel=True), dict(protected=None),
                                  dict(sources=[]), dict(sources=[{'images': []}]),
                                  dict(sources=[{'images': ['https://evil.example/image.jpg']}])])
def test_reader_rejects_unavailable_and_unsafe_data(service, values):
    service.transport.documents['/story-chapter-2-5/'] = reader(**values)
    with pytest.raises(SourceError):
        service.pages('story', 'story-chapter-2-5')


@pytest.mark.parametrize('url', ['http://en-thunderscans.com/a.jpg', 'https://en-thunderscans.com.evil.example/a',
                              'https://localhost/a', 'https://127.0.0.1/a',
                              'https://user:password@en-thunderscans.com/a', 'https://en-thunderscans.com:8080/a',
                              '//en-thunderscans.com/a', 'file:///etc/passwd'])
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


def test_redirect_to_image_and_content_type(monkeypatch):
    responses = iter([FakeResponse(302, {'Location': 'https://en-thunderscans.com/a.jpg'}),
                      FakeResponse(headers={'Content-Type': 'image/jpeg'}, body=b'jpeg')])
    monkeypatch.setattr(requests, 'get', lambda *a, **kw: next(responses))
    assert Transport().get('https://en-thunderscans.com/a.jpg', image=True) == (b'jpeg', 'image/jpeg')


def test_redirect_cannot_reach_internal_host(monkeypatch):
    calls = []
    def get(url, **kwargs):
        calls.append(url)
        return FakeResponse(302, {'Location': 'http://127.0.0.1/secret'})
    monkeypatch.setattr(requests, 'get', get)
    with pytest.raises(SourceError):
        Transport().get('https://en-thunderscans.com/a.jpg', image=True)
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
        Transport().get('https://en-thunderscans.com/a.jpg', image=True)


def test_bounded_download(monkeypatch):
    monkeypatch.setattr(requests, 'get', lambda *a, **kw: FakeResponse(body=b'x' * (4 * 1024 * 1024 + 1)))
    with pytest.raises(SourceError, match='tamanho'):
        Transport().get(BASE_URL)


def test_api_contract_and_invalid_arguments(service):
    client = create_app(service).test_client()
    for route in ['/api/health', '/api/manga/catalog', '/api/manga/search?q=Story',
                  '/api/manga/tags', '/api/manga/story', '/api/manga/story/chapters',
                  '/api/manga/story/chapters/story-chapter-2-5/pages']:
        response = client.get(route)
        assert response.status_code == 200, response.json
        assert response.json['source'] == 'thunderscans'
    for suffix in ['page=0', 'page=501', 'page=NaN', 'source=asura', 'q=' + 'x' * 121]:
        assert client.get('/api/manga/catalog?' + suffix).status_code == 400
    assert client.get('/api/manga/story%3Fbad').status_code == 400
    response = client.get('/api/proxy/image?url=https://en-thunderscans.com/a.jpg')
    assert response.data == b'image-bytes' and response.content_type == 'image/jpeg'
    assert client.get('/api/proxy/image?url=http://localhost').status_code == 400


def test_catalog_native_pagination_and_sidebar_exclusion(service):
    service.transport.documents['/comics/'] += '<div class="hpage"><a class="r" href="?page=2">Next</a></div>'
    # Pagination belongs to the postbody, not a sidebar or unrelated widget.
    service.transport.documents['/comics/'] = service.transport.documents['/comics/'].replace(
        '</div>\n<aside>', '<div class="hpage"><a class="r" href="?page=2">Next</a></div></div>\n<aside>')
    data = service.listing()
    assert [item['id'] for item in data['results']] == ['story']
    assert data['total'] is None and data['has_next'] is True
    assert len(service.transport.calls) == 1
    data['results'].clear()
    assert service.listing()['results']
    assert len(service.transport.calls) == 1


def test_search_and_catalog_request_only_selected_page(service):
    service.listing(2, query='Story & Friends')
    parsed = urlsplit(service.transport.calls[-1])
    assert parsed.path == '/page/2/'
    assert parse_qs(parsed.query)['s'] == ['Story & Friends']
    service.listing(3)
    assert parse_qs(urlsplit(service.transport.calls[-1]).query)['page'] == ['3']
    assert len(service.transport.calls) == 2


def test_genres_and_combined_search_without_detail_requests(service):
    assert service.listing(tag='3', query='story friends')['results'][0]['title'] == 'Story & Friends'
    assert parse_qs(urlsplit(service.transport.calls[-1]).query)['genre[]'] == ['3']
    assert all('/comics/story/' not in url for url in service.transport.calls)
    assert service.listing(tag='3', query='other')['results'] == []
    with pytest.raises(SourceError):
        service.listing(tag='unknown')


def test_confirmed_empty_is_not_a_blocked_page(service):
    service.transport.documents['/'] = '<div class="postbody"><div class="listupd">Not Found</div></div>'
    assert service.listing(query='missing')['results'] == []
    service.transport.documents['/'] = '<html><title>Just a moment</title></html>'
    with pytest.raises(SourceError):
        service.listing(query='blocked')


def test_invalid_next_link_is_not_accepted(service):
    service.transport.documents['/comics/'] = '<div class="postbody"><div class="listupd">' + CARD + '</div><div class="hpage"><a class="r" href="http://127.0.0.1/">Next</a></div></div>'
    with pytest.raises(SourceError):
        service.listing()


def test_wordpress_encoded_unicode_slug_roundtrips_through_api(service):
    identifier = '%e2%98%85the-ultimate-tank-returns%e2%98%85'
    service.transport.documents['/comics/'] = CATALOG.replace('/story/', '/' + identifier + '/')
    service.transport.documents['/comics/' + identifier + '/'] = SERIES
    from urllib.parse import quote
    client = create_app(service).test_client()
    listing = client.get('/api/manga/catalog').json
    assert listing['results'][0]['id'] == identifier
    response = client.get('/api/manga/' + quote(identifier, safe=''))
    assert response.status_code == 200
    assert response.json['id'] == identifier
    assert any('/comics/' + identifier + '/' in url for url in service.transport.calls)


@pytest.mark.parametrize('identifier', ['%2e%2e', '%252fetc', '%5cetc', '%00', '%ff', 'bad%xx'])
def test_encoded_path_traversal_and_invalid_encoding_rejected(service, identifier):
    with pytest.raises(SourceError):
        service.info(identifier)
    assert service.transport.calls == []
