import importlib.util
import json
from pathlib import Path

import pytest

from app import db
from app.libs.library import Library
from app.libs.manga_novel import MangaNovel, SourceUnavailable
from app.libs.source_registry import package_errors
from app.models import SourceReference
from source_registry import load_packages


def package(directory, **changes):
    folder = directory / 'fixture'
    folder.mkdir(parents=True, exist_ok=True)
    data = {'schema_version': 1, 'id': 'fixture', 'name': 'Fixture Scans',
            'api_url': 'http://fixture:3010', 'tags': True, 'search': 'catalog'}
    data.update(changes)
    (folder / 'source.json').write_text(json.dumps(data))
    return folder / 'source.json'


def test_new_source_catalog_search_tags_and_reader(app, api, tmp_path):
    package(tmp_path)
    app.config['SOURCE_PACKAGES_DIR'] = str(tmp_path)
    responses, calls = api
    responses.update({
        '/api/manga/catalog': {'source': 'fixture', 'results': [{'id': 'one', 'title': 'One'}], 'total': 1, 'has_next': False},
        '/api/manga/one': {'source': 'fixture', 'title': 'One'},
        '/api/manga/tags': {'source': 'fixture', 'tags': [{'id': 'action', 'name': 'Action'}]},
        '/api/manga/one/chapters': {'source': 'fixture', 'chapters': [{'id': 'ch1', 'number': '12.5', 'lang': 'en'}]},
        '/api/manga/one/chapters/ch1/pages': {'source': 'fixture', 'pages': ['https://example.org/page.jpg']},
    })
    with app.test_request_context():
        assert Library.sources()['fixture'] == 'Fixture Scans'
        adapter = MangaNovel('fixture')
        listing = adapter.catalog()
        ref = db.session.get(SourceReference, listing['itens'][0]['id'])
        assert adapter.search('One')['itens'][0]['id'] == ref.id
        assert adapter.info(ref)['title'] == 'One'
        assert adapter.tags()[0]['id'] == 'action'
        chapters = adapter.chapters(ref)
        assert chapters[0]['cap'] == '12.5'
        chapter = db.session.get(SourceReference, chapters[0]['cap_id'])
        assert adapter.pages(chapter, ref)[0].startswith('/img/page/proxy?')
        assert SourceReference.query.count() == 2
    response = app.test_client().get('/sources')
    assert response.status_code == 200
    assert b'Fixture Scans' in response.data
    assert b'Browse source' in response.data
    response = app.test_client().get('/tags?source=fixture')
    assert response.status_code == 200
    assert b'Action' in response.data


@pytest.mark.parametrize('changes', [
    {'schema_version': 2}, {'id': 'asura'}, {'id': '../escape'},
    {'api_url': 'file:///etc/passwd'}, {'api_url': 'http://user:secret@example.org'},
    {'enabled': 'false'}, {'api_url': None}, {'api_url': []}, {'chapter_languages': ['xx']}, {'search': 'unknown'},
    {'service': {'image': 'example:1', 'port': 3000}},
    {'api_url': '', 'service': {'image': '${UNSAFE}', 'port': 3000}},
    {'api_url': '', 'service': {'image': 'example:1', 'port': True}},
    {'command': 'anything'},
])
def test_invalid_packages_are_isolated(tmp_path, changes):
    package(tmp_path, **changes)
    sources, errors = load_packages(tmp_path)
    assert not sources
    assert len(errors) == 1
    assert 'secret' not in errors[0]['message']


def test_live_discovery_disable_and_remove_preserves_references(app, api, tmp_path):
    app.config['SOURCE_PACKAGES_DIR'] = str(tmp_path)
    with app.app_context():
        assert 'fixture' not in Library.sources()
    path = package(tmp_path)
    api[0]['/api/manga/catalog'] = {'source': 'fixture', 'results': [{'id': 'one', 'title': 'One'}]}
    with app.app_context():
        identifier = MangaNovel('fixture').catalog()['itens'][0]['id']
    package(tmp_path, enabled=False)
    with app.app_context():
        assert 'fixture' not in Library.sources()
        with pytest.raises(SourceUnavailable):
            MangaNovel('fixture')
        assert db.session.get(SourceReference, identifier)
        assert Library().id2Cover(identifier) == '/static/img/cover-placeholder.svg'
    path.unlink()
    with app.app_context():
        with pytest.raises(SourceUnavailable):
            MangaNovel('fixture')
        assert db.session.get(SourceReference, identifier)
    path.write_text('not json')
    with app.app_context():
        assert 'mangadex' in Library.sources()
        assert package_errors()[0]['message'] == 'Invalid JSON'


def test_compose_services_are_restricted_and_disabled_packages_omitted(tmp_path):
    spec = importlib.util.spec_from_file_location('source_compose', Path(__file__).resolve().parents[1] / 'scripts/source-compose.py')
    compiler = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(compiler)
    package(tmp_path, api_url='', service={'image': 'example/provider:1.0', 'port': 3010})
    result = compiler.compile_services(tmp_path)
    service = result['services']['source-fixture']
    assert service['image'] == 'example/provider:1.0'
    assert 'volumes' not in service and 'ports' not in service
    assert service['cap_drop'] == ['ALL']
    assert load_packages(tmp_path)[0][0].api_url == 'http://source-fixture:3010'
    package(tmp_path, enabled=False)
    assert compiler.compile_services(tmp_path) == {'services': {}}
    package(tmp_path, api_url='invalid')
    with pytest.raises(ValueError):
        compiler.compile_services(tmp_path)
