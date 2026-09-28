"""English application copy must not change provider data or stored identities."""
import pytest
from app import db
from app.libs.canonical import resolve_work, sync_chapters
from app.libs.identity import chapter_identity
from app.models import User
from conftest import manga_record


@pytest.mark.parametrize('path,heading', [
    ('/auth/login', 'Sign in'), ('/auth/register', 'Create account'),
    ('/status', 'Service diagnostics'), ('/static/offline.html', 'You are offline'),
])
def test_english_public_pages(app, path, heading):
    response = app.test_client().get(path)
    assert response.status_code == 200
    assert '<html lang="en">' in response.text
    assert heading in response.text


def test_registration_validation_in_english(app):
    response = app.test_client().post('/auth/register', data={
        'username': 'reader', 'email': 'reader@example.test',
        'password': 'password-one', 'password_repeat': 'password-two',
    })
    assert 'Passwords must match.' in response.text
    with app.app_context():
        assert User.query.count() == 0


def test_english_tags_keep_original_titles_and_chapter_languages(app, api):
    responses, _ = api
    record = manga_record()
    record['relationships'] = []
    record['attributes']['tags'] = [{
        'id': 'action', 'type': 'tag', 'attributes': {
            'name': {'pt-br': 'Ação', 'en': 'Action'}, 'description': {},
            'group': 'genre', 'version': 1,
        },
    }]
    responses['/manga/m1'] = {'data': record}
    responses['/manga/m1/aggregate'] = lambda params: {'volumes': {'1': {'chapters': {
        '1': {'id': params['translatedLanguage[]'][0] + '-1', 'chapter': '1', 'others': []},
    }}}}
    response = app.test_client().get('/manga/m1')
    assert response.status_code == 200
    assert 'Título traduzido' in response.text
    assert 'Browse manga tagged Action' in response.text
    assert 'Portuguese (Brazil)' in response.text
    assert 'Portuguese (Portugal)' in response.text
    assert 'English' in response.text


def test_english_unnumbered_chapters_reuse_legacy_identity(context):
    sw = resolve_work({'id': 'a', 'title': 'Original title'}, 'asura')
    old = sync_chapters(sw, [{'cap_id': 'chapter', 'cap': 'Sem número'}])[0]
    logical_id = old.logical_chapter_id
    db.session.commit()
    new = sync_chapters(sw, [{'cap_id': 'chapter', 'cap': 'Unnumbered'}])[0]
    assert new.logical_chapter_id == logical_id
    assert chapter_identity('Sem número', discriminator='chapter')[0] == chapter_identity(
        'Unnumbered', discriminator='chapter')[0]


def test_legacy_placeholders_are_translated_without_rewriting_data(app, monkeypatch):
    from app.libs.library import Library
    with app.app_context():
        sw = resolve_work({'id': 'old', 'title': 'Sem título', 'sinopse': 'Sem descrição'}, 'asura')
        work_id = sw.work_id
        db.session.commit()
    monkeypatch.setattr(Library, 'sources', staticmethod(lambda: {'mangadex': 'MangaDex'}))
    response = app.test_client().get('/work/' + work_id)
    assert response.status_code == 200
    assert '<h1>Untitled</h1>' in response.text
    assert 'No description available' in response.text
    with app.app_context():
        from app.models import Work
        assert db.session.get(Work, work_id).canonical_title == 'Sem título'
