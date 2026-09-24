from copy import deepcopy
from urllib.parse import parse_qs, urlsplit
import json

import pytest
import requests
from cachelib import SimpleCache

from app import create_app, db, cache


class TestConfig:
    TESTING = True
    SECRET_KEY = 'test-only'
    SQLALCHEMY_DATABASE_URI = 'sqlite://'
    CACHE_TYPE = 'SimpleCache'
    SESSION_TYPE = 'cachelib'
    SESSION_CACHELIB = SimpleCache()
    WTF_CSRF_ENABLED = False


@pytest.fixture
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        cache.clear()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()
        cache.clear()


@pytest.fixture
def context(app):
    with app.test_request_context():
        yield


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError('Unexpected network request')
    monkeypatch.setattr(requests.sessions.Session, 'request', blocked)


def manga_record(identifier='m1'):
    return {'id': identifier, 'type': 'manga', 'attributes': {
        'title': {'ja': 'Original'}, 'altTitles': [{'pt-br': 'Título traduzido'}],
        'description': {'pt-br': 'Descrição'}, 'links': {}, 'originalLanguage': 'ja',
        'lastVolume': None, 'lastChapter': None, 'publicationDemographic': None,
        'status': 'ongoing', 'year': 2024, 'contentRating': 'safe', 'tags': [],
        'createdAt': '2024-01-01T00:00:00Z', 'updatedAt': '2024-01-01T00:00:00Z'},
        'relationships': [{'type': 'author', 'id': 'a1'}]}


@pytest.fixture
def api(monkeypatch):
    calls = []
    responses = {}

    def get(url, **kwargs):
        parsed = urlsplit(url)
        params = parse_qs(parsed.query)
        calls.append((parsed.path, params))
        value = responses[parsed.path]
        if callable(value):
            value = value(params)
        response = requests.Response()
        response.status_code = 200
        response._content = json.dumps(deepcopy(value)).encode()
        return response

    monkeypatch.setattr(requests, 'get', get)
    return responses, calls
