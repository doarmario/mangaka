import json
from urllib.parse import parse_qs, urlsplit

import pytest
import requests
from flask_login import login_user, logout_user
from mangadex.errors import ApiError

from app import cache, db
from app.libs.md import Mangas
from app.models import User, Manga, Chapter, Readed
from conftest import manga_record


@pytest.mark.parametrize('method,args', [
    ('listAll', ()), ('listRecents', ()),
    ('listMangaByTag', ('tag1',)), ('searchMangaByTitle', ('test',))])
def test_lists_keep_totals_and_cache_each_page(context, api, method, args):
    responses, calls = api
    responses['/manga'] = lambda p: {'data': [manga_record(p['offset'][0])], 'total': 47}
    service = Mangas()
    call = getattr(service, method)
    first, second = call(*args, 0), call(*args, 20)
    assert first['total'] == second['total'] == 47
    assert first['itens'][0] == {'id': '0', 'title': 'Título traduzido',
                                 'aliases': ['Original', 'Título traduzido'], 'ano': 2024}
    assert second['itens'][0]['id'] == '20'
    assert call(*args, 0) == first
    assert len(calls) == 2
    assert calls[0][1]['availableTranslatedLanguage[]'] == ['pt-br', 'pt', 'en']
    json.dumps(first)


def test_cache_varies_with_language_and_limit(context, api):
    responses, calls = api
    responses['/manga'] = {'data': [], 'total': 0}
    for service in [Mangas(), Mangas(lang='en'), Mangas(limit=10)]:
        service.listAll(0)
        service.listAll(0)
    assert len(calls) == 3


def test_total_reuses_first_page(context, api):
    responses, calls = api
    responses['/manga'] = {'data': [], 'total': 0}
    service = Mangas()
    assert service.getTotalPages() == 0
    assert service.listaGeral() == {'itens': [], 'total': 0}
    assert len(calls) == 1


def reader_responses(responses, chapter='c2'):
    responses['/manga/m1'] = {'data': manga_record()}
    responses['/manga/m1/aggregate'] = {'volumes': {'1': {'chapters': {
        '1': {'chapter': '1', 'id': 'c1', 'others': []},
        '2': {'chapter': '2', 'id': 'c2', 'others': ['alternative']},
        '3': {'chapter': '3', 'id': 'c3', 'others': []}}}}}
    aggregate = responses['/manga/m1/aggregate']
    responses['/manga/m1/aggregate'] = lambda p: aggregate if p['translatedLanguage[]'] == ['pt-br'] else {'volumes': {}}
    responses['/chapter/' + chapter] = {'data': {'id': chapter, 'type': 'chapter',
        'attributes': {'title': None, 'volume': '1', 'chapter': '2', 'translatedLanguage': 'pt-br'},
        'relationships': [{'type': 'manga', 'id': 'm1'}]}}
    responses['/at-home/server/' + chapter] = {'baseUrl': 'https://images.example',
        'chapter': {'hash': 'hash', 'data': ['a&b.jpg']}}


@pytest.mark.parametrize('chapter,prev,nxt', [
    ('c1', None, 'c2'), ('c2', 'c1', 'c3'), ('c3', 'c2', None),
    ('alternative', 'c1', 'c3'), ('unlisted', None, None)])
def test_reader_boundaries_and_alternative_chapters(context, api, chapter, prev, nxt):
    responses, calls = api
    reader_responses(responses, chapter)
    service = Mangas()
    data = service.getChapter(chapter)
    assert (data['prev'], data['next']) == (prev, nxt)
    assert data['manga'] == 'Título traduzido'
    assert parse_qs(urlsplit(data['pages'][0]).query)['url'] == ['https://images.example/data/hash/a&b.jpg']
    assert service.getChapter(chapter) == data
    assert len(calls) == 4
    cache.delete(service._key('pages', chapter))
    service.getChapter(chapter)
    assert len(calls) == 5
    assert calls[-1][0] == '/at-home/server/' + chapter


def test_aggregate_accepts_special_and_missing_numbers(context, api):
    responses, calls = api
    responses['/manga/m1/aggregate'] = {'volumes': {'none': {'chapters': {
        str(i): {'chapter': num, 'id': str(i)}
        for i, num in enumerate([None, 'extra', '2.5', '10', 'none'])}}, 'empty': {'chapters': []}}}
    chapters = Mangas(lang='pt-br').getMangaChapterList('m1')
    assert [c['cap'] for c in chapters] == ['10', '2.5', 'Sem número', 'extra', 'Sem número']


def test_user_read_state_never_enters_shared_cache(context, api):
    responses, _ = api
    reader_responses(responses)
    user = User(username='one', email='one@example.com', password_hash='unused')
    manga = Manga(uuid='m1', title='Title')
    chapter = Chapter(uuid='c2', manga=manga)
    db.session.add_all([user, chapter])
    db.session.flush()
    db.session.add(Readed(user_id=user.id, chapter_id=chapter.id))
    db.session.commit()
    service = Mangas()
    login_user(user)
    assert any(c['is_readed'] for c in service.getMangaChapterList('m1'))
    assert not any(c['is_readed'] for c in cache.get(service._key('chapters', 'm1', 'pt-br')))
    logout_user()
    assert not any(c['is_readed'] for c in service.getMangaChapterList('m1'))


def test_details_description_and_author_cache(context, api, monkeypatch):
    responses, _ = api
    reader_responses(responses)
    service = Mangas()
    from types import SimpleNamespace
    calls = []
    def author(author_id):
        calls.append(author_id)
        return SimpleNamespace(name='Author')
    monkeypatch.setattr(service.author, 'get_author_by_id', author)
    assert service.showManga('m1')['sinopse'] == 'Descrição'
    assert service.showManga('m1')['autor'] == 'Author'
    assert calls == ['a1']
    assert service.id2Cover('m1') == '/static/img/page.png'
    json.dumps(cache.get(service._key('manga', 'm1')))


def test_rate_limit_blocks_new_requests_but_serves_cache(context, api, monkeypatch):
    responses, calls = api
    responses['/manga'] = {'data': [], 'total': 0}
    service = Mangas()
    service.listAll(0)
    response = requests.Response()
    response.status_code = 429
    response.headers['Retry-After'] = '30'
    from mangadex.url_models import URLRequest
    requests_made = []
    def limited(*args, **kwargs):
        requests_made.append(args)
        raise ApiError(response)
    monkeypatch.setattr(URLRequest, 'request_url', limited)
    with pytest.raises(ApiError):
        service.listAll(20)
    with pytest.raises(ApiError):
        service.searchMangaByTitle('new')
    assert service.listAll(0)['total'] == 0
    assert len(requests_made) == 1


def test_network_failure_is_not_cached(context, api, monkeypatch):
    from mangadex.url_models import URLRequest
    real = URLRequest.request_url
    def timeout(*args, **kwargs):
        raise requests.Timeout()
    monkeypatch.setattr(URLRequest, 'request_url', timeout)
    with pytest.raises(requests.Timeout):
        Mangas().listAll(0)
    monkeypatch.setattr(URLRequest, 'request_url', real)
    api[0]['/manga'] = {'data': [], 'total': 0}
    assert Mangas().listAll(0)['total'] == 0


def test_listing_primes_metadata_cache(context, api):
    responses, calls = api
    responses['/manga'] = {'data': [manga_record()], 'total': 1}
    service = Mangas()
    service.listAll(0)
    assert service.getManga('m1')['sinopse'] == 'Descrição'
    assert service.id2Cover('m1') == '/static/img/page.png'
    assert len(calls) == 1


def test_recent_history_does_not_mix_users_with_identical_timestamps(context):
    from datetime import datetime
    one = User(username='one', email='one@example.com', password_hash='unused')
    two = User(username='two', email='two@example.com', password_hash='unused')
    manga = Manga(uuid='m1', title='Title')
    first = Chapter(uuid='c1', manga=manga)
    second = Chapter(uuid='c2', manga=manga)
    db.session.add_all([one, two, first, second])
    db.session.flush()
    stamp = datetime(2024, 1, 1)
    db.session.add_all([
        Readed(user_id=one.id, chapter_id=first.id, updated_at=stamp),
        Readed(user_id=two.id, chapter_id=second.id, updated_at=stamp)])
    db.session.commit()
    login_user(one)
    assert Mangas().continuar_lendo(0) == [{'id': 'm1', 'title': 'Title', 'chapter': 'c1'}]


def test_languages_keep_same_number_translations_and_cache_separately(context, api):
    responses, calls = api
    def aggregate(params):
        language = params['translatedLanguage[]'][0]
        return {'volumes': {'1': {'chapters': {'1': {
            'chapter': '1', 'id': language + '-1', 'others': []}}}}}
    responses['/manga/m1/aggregate'] = aggregate
    service = Mangas()
    chapters = service.getMangaChapterList('m1')
    assert {c['language'] for c in chapters} == {'pt-br', 'pt', 'en'}
    assert len(chapters) == 3
    assert len(calls) == 3
    english = service.getMangaChapterList('m1', language='en')
    assert [c['cap_id'] for c in english] == ['en-1']
    assert len(calls) == 3


def test_reader_keeps_english_navigation(context, api):
    responses, calls = api
    reader_responses(responses, 'en-2')
    responses['/chapter/en-2']['data']['attributes']['translatedLanguage'] = 'en'
    def aggregate(params):
        language = params['translatedLanguage[]'][0]
        return {'volumes': {'1': {'chapters': {
            str(n): {'chapter': str(n), 'id': f'{language}-{n}', 'others': []}
            for n in [1, 2, 3]}}}}
    responses['/manga/m1/aggregate'] = aggregate
    result = Mangas().getChapter('en-2')
    assert result['language_name'] == 'English'
    assert (result['prev'], result['next']) == ('en-1', 'en-3')
    aggregates = [params for path, params in calls if path.endswith('/aggregate')]
    assert aggregates == [{'translatedLanguage[]': ['en']}]
