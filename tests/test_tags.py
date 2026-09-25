from conftest import manga_record

TAG = {'id': 'isekai-id', 'type': 'tag', 'attributes': {
    'name': {'en': 'Isekai'}, 'description': {}, 'group': 'theme', 'version': 1}}


def setup_api(api):
    responses, calls = api
    record = manga_record()
    record['attributes']['tags'] = [TAG]
    record['relationships'] = []
    responses['/manga/tag'] = {'data': [TAG]}
    responses['/manga'] = {'data': [record], 'total': 45}
    responses['/manga/m1'] = {'data': record}
    responses['/manga/m1/aggregate'] = {'volumes': []}
    return calls


def test_manga_tags_link_to_filtered_catalog(app, api):
    setup_api(api)
    response = app.test_client().get('/manga/m1')
    assert response.status_code == 200
    assert 'source=mangadex&amp;tag=isekai-id' in response.text
    assert 'Ver mangás de Isekai' in response.text


def test_tags_page_lists_and_links_mangadex_tags(app, api):
    setup_api(api)
    response = app.test_client().get('/tags')
    assert response.status_code == 200
    assert 'Tags' in response.text
    assert 'Isekai' in response.text
    assert '/mangas?tag=isekai-id' in response.text


def test_tag_filter_keeps_pagination_and_cache(app, api):
    calls = setup_api(api)
    client = app.test_client()
    first = client.get('/mangas?tag=isekai-id')
    assert first.status_code == 200
    assert 'Tag: <strong>Isekai</strong>' in first.text
    assert '/mangas/2?source=mangadex&amp;tag=isekai-id' in first.text
    assert 'Remover filtro' in first.text
    second = client.get('/mangas/2?tag=isekai-id')
    assert second.status_code == 200
    assert calls[-1][1]['includedTags[]'] == ['isekai-id']
    assert calls[-1][1]['offset'] == ['20']
    count = len(calls)
    client.get('/mangas/2?tag=isekai-id')
    assert len(calls) == count
    client.get('/mangas')
    assert 'includedTags[]' not in calls[-1][1]


def test_search_combines_title_and_tag(app, api):
    calls = setup_api(api)
    response = app.test_client().get('/search?query=story&tag=isekai-id')
    assert response.status_code == 200
    assert calls[-1][1]['title'] == ['story']
    assert calls[-1][1]['includedTags[]'] == ['isekai-id']
    assert 'name="tag" value="isekai-id"' in response.text
    assert 'tag=isekai-id' in response.text


def test_unknown_tag_does_not_load_unfiltered_catalog(app, api):
    calls = setup_api(api)
    assert app.test_client().get('/mangas?tag=unknown').status_code == 404
    assert not any(path == '/manga' for path, _ in calls)


def test_asura_tag_is_validated_and_forwarded(app, monkeypatch):
    import requests
    app.config['MANGA_NOVEL_API_URL'] = 'http://source-api:3001'
    calls = []
    def get(url, params, timeout):
        calls.append((url, params))
        response = requests.Response()
        response.status_code = 200
        if url.endswith('/tags'):
            data = {'tags': [{'id': 'isekai', 'name': 'Isekai'}]}
        else:
            assert params['tag'] == 'isekai'
            data = {'results': [{'slug': 'comics/story', 'title': 'Story'}], 'total': 40, 'has_next': True}
        response.json = lambda: {'source': 'asura', **data}
        return response
    monkeypatch.setattr(requests, 'get', get)
    response = app.test_client().get('/mangas?source=asura&tag=isekai')
    assert response.status_code == 200
    assert '/mangas/2?source=asura&amp;tag=isekai' in response.text
    assert 'Isekai' in response.text
    response = app.test_client().get('/search?source=asura&tag=isekai&query=story')
    assert response.status_code == 200
    assert calls[-1][1]['q'] == 'story'
    assert app.test_client().get('/mangas?source=asura&tag=unknown').status_code == 404
