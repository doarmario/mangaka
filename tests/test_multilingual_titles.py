import importlib.util
from alembic.migration import MigrationContext
from alembic.operations import Operations
from app import db
from app.libs.canonical import resolve_work
from app.libs.identity import title_keys, title_variants
from app.libs.md import Mangas
from app.libs.manga_novel import MangaNovel, register_many
from app.models import WorkAlias, SourceReference
from conftest import manga_record


TITLES = {
    'pt': 'A História', 'pt-br': 'Uma História', 'en': 'The Story',
    'ja': '物語', 'ja-ro': 'Monogatari', 'ko': '이야기', 'ko-ro': 'Iyagi',
    'zh': '故事', 'zh-hk': '傳說',
}


def test_mangadex_keeps_all_languages_in_listing_and_storage(context, api):
    record = manga_record()
    record['attributes']['title'] = {'en': 'The Story'}
    record['attributes']['altTitles'] = [{lang: title} for lang, title in TITLES.items()]
    api[0]['/manga'] = {'data': [record], 'total': 1}
    item = Mangas().listaGeral()['itens'][0]
    sw = resolve_work(item, 'mangadex')
    db.session.commit()
    variants = sw.work.metadata_json['titles']
    assert {(v['language'], v['title']) for v in variants} == set(TITLES.items())
    assert {v['source'] for v in variants} == {'mangadex'}
    for title in TITLES.values():
        assert title_keys({'title': title}) & title_keys({'titles': variants})
    # Chapters still request only the user's reading languages.
    assert api[1][0][1]['availableTranslatedLanguage[]'] == ['pt-br', 'pt', 'en']


def test_raw_variants_survive_normalized_dedup_and_refresh(context):
    variants = ['Solo Leveling', 'SOLO LEVELING', 'Solo-Leveling', 'Ｓｏｌｏ Ｌｅｖｅｌｉｎｇ']
    item = {'id': 'a', 'title': variants[0], 'titles': [
        {'title': title, 'language': 'en'} for title in variants]}
    for _ in range(2):
        sw = resolve_work(item, 'asura')
        db.session.commit()
    assert WorkAlias.query.count() == 1  # Matching index only.
    assert [v['title'] for v in sw.work.metadata_json['titles']] == variants
    resolve_work({'id': 'a', 'title': variants[0]}, 'asura')
    db.session.commit()
    assert [v['title'] for v in sw.work.metadata_json['titles']] == variants


def test_same_spelling_in_two_languages_and_unknown_language():
    variants = title_variants({'title': 'Solo Leveling', 'aliases': ['Unlabelled'],
        'titles': [{'title': 'Solo Leveling', 'language': 'en'},
                   {'title': 'Solo Leveling', 'language': 'pt-br'}]}, 'mangadex')
    assert {v['language'] for v in variants if v['title'] == 'Solo Leveling'} == {'en', 'pt-br'}
    assert next(v for v in variants if v['title'] == 'Unlabelled')['language'] is None


def test_source_adapter_preserves_list_and_detail_titles(context, monkeypatch):
    from flask import current_app
    current_app.config['MANGA_NOVEL_API_URL'] = 'http://unused'
    raw = {'id': 'story', 'title': 'Story', 'aliases': ['物語'],
           'titles': [{'title': '物語', 'language': 'ja'}]}
    adapter = MangaNovel('asura')
    item = adapter._normalize_list([raw], 1, False)['itens'][0]
    assert item['aliases'] == ['物語'] and item['titles'] == raw['titles']
    monkeypatch.setattr(adapter, '_request', lambda *args, **kwargs: raw)
    details = adapter.info(db.session.get(SourceReference, item['id']))
    assert {'title': '物語', 'language': 'ja', 'source': None} in details['titles']


def test_work_merge_keeps_languages_and_sources(context):
    a = resolve_work({'id': 'a', 'title': 'Original', 'titles': [{'title': '原作', 'language': 'ja'}]}, 'asura')
    db.session.commit()
    b = resolve_work({'id': 'b', 'title': 'Translation', 'titles': [{'title': '번역', 'language': 'ko'}]}, 'qiscans')
    db.session.commit()
    resolve_work({'id': 'b', 'title': 'Translation', 'aliases': ['Original']}, 'qiscans')
    db.session.commit()
    db.session.refresh(a)
    pairs = {(v['title'], v['language'], v['source']) for v in a.work.metadata_json['titles']}
    assert ('原作', 'ja', 'asura') in pairs
    assert ('번역', 'ko', 'qiscans') in pairs


def test_data_migration_recovers_local_titles_and_is_idempotent(context):
    ref = register_many('asura', 'manga', [('story', {'title': 'Story',
        'aliases': ['STORY'], 'titles': [{'title': '物語', 'language': 'ja'}]})])[0]
    sw = resolve_work({'id': ref.id, 'title': 'Story'}, 'asura')
    sw.work.metadata_json = {}
    db.session.commit()
    spec = importlib.util.spec_from_file_location('titles_migration', 'migrations/versions/20260928_multilingual_titles.py')
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with db.engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            migration.downgrade()
            migration.upgrade()
    db.session.expire_all()
    variants = sw.work.metadata_json['titles']
    assert {(v['title'], v['language']) for v in variants} == {('Story', None), ('STORY', None), ('物語', 'ja')}


def test_api_exposes_language_and_source(app):
    with app.app_context():
        sw = resolve_work({'id': 'a', 'title': 'Story', 'titles': [
            {'title': '物語', 'language': 'ja'}]}, 'asura')
        db.session.commit()
        identifier = sw.work_id
    data = app.test_client().get('/api/works/' + identifier).json
    assert {'title': '物語', 'language': 'ja', 'source': 'asura'} in data['titles']
