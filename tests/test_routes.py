import pytest
import requests
from mangadex.errors import ApiError
from app.routes import manga as routes
from conftest import manga_record
from test_mangadex import reader_responses


@pytest.mark.parametrize('total,page,offset', [
    (47, 1, 0), (47, 3, 40), (47, 99, 40), (0, 1, 0), (15000, 9999, 9980)])
def test_catalog_pagination(app, api, total, page, offset):
    responses, calls = api
    responses['/manga'] = {'data': [manga_record()], 'total': total}
    response = app.test_client().get('/mangas/' + str(page), follow_redirects=True)
    assert response.status_code == 200
    assert calls[-1][1]['offset'] == [str(offset)]
    if offset == 0:
        assert len(calls) == 1
    if page == 3:
        assert b'/mangas/2' in response.data
        assert b'/mangas/4' not in response.data


def test_search_keeps_query_and_previous_link_on_last_page(app, api):
    responses, calls = api
    responses['/manga'] = {'data': [manga_record()], 'total': 21}
    response = app.test_client().get('/search/2?query=One+Piece')
    assert response.status_code == 200
    assert b'/search/1?query=One+Piece' in response.data or b'/search?query=One+Piece' in response.data
    assert calls[-1][1]['offset'] == ['20']
    assert calls[-1][1]['title'] == ['One Piece']


def test_catalog_filters_keep_language_and_status(app, api):
    responses, calls = api
    responses['/manga'] = {'data': [manga_record()], 'total': 1}
    response = app.test_client().get('/mangas?language=en&status=completed')
    assert response.status_code == 200
    assert calls[-1][1]['availableTranslatedLanguage[]'] == ['en']
    assert calls[-1][1]['status[]'] == ['completed']
    assert 'name="language"' in response.text
    assert 'name="status"' in response.text


def test_unlisted_chapter_renders_without_none_links(app, api):
    reader_responses(api[0], 'unlisted')
    response = app.test_client().get('/cap/unlisted')
    assert response.status_code == 200
    assert b'/cap/None' not in response.data


@pytest.mark.parametrize('error,status', [
    (ApiError({'status': 429, 'reason': 'limited'}), 503),
    (ApiError({'status': 500, 'reason': 'unavailable'}), 502),
    (requests.Timeout(), 503)])
def test_upstream_errors_render_controlled_response(app, monkeypatch, error, status):
    def fail():
        raise error
    monkeypatch.setattr(routes.manga, 'getTotalPages', fail)
    response = app.test_client().get('/mangas')
    assert response.status_code == status
    assert 'MangaDex' in response.text


def test_get_search_works_with_csrf_enabled(app, api):
    app.config['WTF_CSRF_ENABLED'] = True
    api[0]['/manga'] = {'data': [], 'total': 0}
    assert app.test_client().get('/search?query=test').status_code == 200


def test_library_requires_authentication(app):
    response = app.test_client().get('/biblioteca')
    assert response.status_code == 302
    assert '/auth/login' in response.headers['Location']


def test_status_page_reports_local_components(app):
    response = app.test_client().get('/status')
    assert response.status_code == 200
    assert 'Banco de dados' in response.text
    assert 'Cache' in response.text
    assert 'Worker de novidades' in response.text


def test_service_worker_is_available(app):
    response = app.test_client().get('/service-worker.js')
    assert response.status_code == 200
    assert 'Service-Worker-Allowed' in response.headers
    assert 'mangaka-shell-v1' in response.text


def test_security_headers_are_present(app):
    response = app.test_client().get('/status')
    assert response.headers['X-Content-Type-Options'] == 'nosniff'
    assert response.headers['X-Frame-Options'] == 'SAMEORIGIN'
    assert response.headers['Referrer-Policy'] == 'strict-origin-when-cross-origin'


def test_notifications_refresh_requires_authentication(app):
    response = app.test_client().get('/notificacoes/atualizar')
    assert response.status_code == 302
    assert '/auth/login' in response.headers['Location']


def test_notifications_mark_all_requires_authentication(app):
    response = app.test_client().post('/notificacoes/marcar-todas')
    assert response.status_code == 302
    assert '/auth/login' in response.headers['Location']


def test_notifications_count_requires_authentication(app):
    response = app.test_client().get('/api/notificacoes/count')
    assert response.status_code == 302
    assert '/auth/login' in response.headers['Location']


def test_init_db_command_preserves_existing_data(app):
    from app import db
    from app.models import User
    with app.app_context():
        db.session.add(User(username='existing', email='existing@example.com', password_hash='unused'))
        db.session.commit()
    runner = app.test_cli_runner()
    for _ in range(2):
        result = runner.invoke(args=['init-db'])
        assert result.exit_code == 0
    with app.app_context():
        assert User.query.filter_by(username='existing').count() == 1


def test_manga_shows_language_selector_and_prefers_portuguese(app, api):
    responses, _ = api
    record = manga_record()
    record['relationships'] = []
    responses['/manga/m1'] = {'data': record}
    responses['/manga/m1/aggregate'] = lambda p: {'volumes': {'1': {'chapters': {
        '1': {'id': p['translatedLanguage[]'][0] + '-1', 'chapter': '1', 'others': []}}}}}
    response = app.test_client().get('/manga/m1')
    assert response.status_code == 200
    assert 'Português (Brasil)' in response.text
    assert 'Português (Portugal)' in response.text
    assert 'English' in response.text
    assert 'id="chapter-language"' in response.text
    assert 'id="start-reading" class="button primary" href="/cap/pt-br-1"' in response.text


def test_start_reading_falls_back_to_english(app, api):
    responses, _ = api
    record = manga_record()
    record['relationships'] = []
    responses['/manga/m1'] = {'data': record}
    responses['/manga/m1/aggregate'] = lambda p: {'volumes': {'1': {'chapters': {
        '1': {'id': 'en-1', 'chapter': '1', 'others': []}}}}} if p['translatedLanguage[]'] == ['en'] else {'volumes': []}
    response = app.test_client().get('/manga/m1')
    assert response.status_code == 200
    assert 'id="start-reading" class="button primary" href="/cap/en-1"' in response.text
