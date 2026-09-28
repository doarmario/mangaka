from decimal import Decimal
import importlib.util
import pytest
from app import db
from app.libs.identity import normalize_title, parse_chapter, chapter_order, match_confidence, approximate_page
from app.libs.canonical import resolve_work, sync_chapters, backfill
from app.libs.reading import save_progress, resolve_source_for_chapter, toggle_favorite
from app.models import (Work, SourceWork, SourceChapter, WorkAlias, LogicalChapter, ReadingProgress,
                        User, Manga, Chapter, Favorite, Readed, SourceReference)
from app.libs.library import Library
from app.libs.manga_novel import SourceUnavailable


def work(source, identifier, title='Solo Leveling', **extra):
    row = resolve_work({'id': identifier, 'title': title, **extra}, source)
    db.session.commit()
    return row


def chapter(sw, identifier, number='50', **extra):
    row = sync_chapters(sw, [{'cap_id': identifier, 'cap': number, 'language': 'en', **extra}])[0]
    db.session.commit()
    return row


def user():
    row = User(username='reader', email='reader@example.test', password_hash='unused')
    db.session.add(row)
    db.session.commit()
    return row


@pytest.mark.parametrize('title', ['Solo Leveling', ' solo   leveling ', 'SOLO LEVELING', 'Ｓｏｌｏ　Ｌｅｖｅｌｉｎｇ'])
def test_normalization(title):
    assert normalize_title(title) == 'solo leveling'


def test_normalization_not_overaggressive():
    assert normalize_title('A+') != normalize_title('A')
    assert normalize_title('é') != normalize_title('e')
    assert normalize_title('Story 2') != normalize_title('Story')


@pytest.mark.parametrize('extra', [dict(type='novel'), dict(year=2025), dict(author='Other'),
                                   dict(country='kr'), dict(edition='remake')])
def test_metadata_conflicts_do_not_merge(context, extra):
    first = work('a', 'a', type='manga', year=2020, author='Original', country='jp', edition='original')
    second = work('b', 'b', **extra)
    assert first.work_id != second.work_id


@pytest.mark.parametrize('title', ['Solo Leveling Ragnarok', 'Solo Leveling 2', 'Solo Leveling Remake', 'Solo Leveling Side Story', 'Solo Levelling'])
def test_similar_titles_never_auto_merge(context, title):
    first = work('a', 'a')
    second = work('b', 'b', title)
    assert first.work_id != second.work_id
    assert match_confidence({'title': 'Solo Leveling'}, {'title': title})[0] < 1


def test_alias_and_idempotent_sources(context):
    a = work('a', 'a', aliases=['I Alone Level Up', '나 혼자만 레벨업'])
    b = work('b', 'b', 'I Alone Level Up')
    c = work('c', 'c', '나 혼자만 레벨업')
    assert a.work_id == b.work_id == c.work_id
    for _ in range(2):
        work('b', 'b', 'I Alone Level Up')
    assert Work.query.count() == 1
    assert SourceWork.query.count() == 3
    assert WorkAlias.query.count() == 3


def test_external_id_matches_unrelated_translations(context):
    a = work('a', 'a', external_ids={'anilist': '123'})
    b = work('b', 'b', 'Tradução diferente', external_ids={'anilist': '123'})
    assert a.work_id == b.work_id


def test_same_source_duplicate_title_and_ambiguity(context):
    a = work('a', 'a')
    a2 = work('a', 'a2')
    b = work('b', 'b')
    assert len({a.work_id, a2.work_id, b.work_id}) == 3


@pytest.mark.parametrize('raw,key,number', [('12', '12', Decimal(12)), ('12.1', '12.1', Decimal('12.1')),
    ('12.5', '12.5', Decimal('12.5')), ('12.5.1', '12.5.1', None), ('0', '0', Decimal(0)),
    ('0.0', '0', Decimal(0)), ('012.50', '12.5', Decimal('12.5')), ('Prologue', 'prologue', None),
    ('Extra', 'extra', None), ('Side Story 3', 'side story 3', None), ('Epilogue', 'epilogue', None)])
def test_chapter_parser(raw, key, number):
    assert parse_chapter(raw) == (key, number)


def test_natural_chapter_order():
    values = ['13', '12.5.1', '12.1', '12', '12.5', '0', 'Prologue', 'Epilogue', 'Side Story 10', 'Side Story 3']
    assert sorted(values, key=chapter_order) == ['Prologue', '0', '12', '12.1', '12.5', '12.5.1', '13', 'Side Story 3', 'Side Story 10', 'Epilogue']


def test_chapter_equivalence_specials_volumes(context):
    a, b = work('a', 'a'), work('b', 'b')
    assert chapter(a, 'a12', '12.50').logical_chapter_id == chapter(b, 'b12', '12.5').logical_chapter_id
    assert chapter(a, 'ap', 'Prologue').logical_chapter_id == chapter(b, 'bp', 'Prologue').logical_chapter_id
    assert chapter(a, 'ax', 'Extra').logical_chapter_id != chapter(b, 'bx', 'Extra').logical_chapter_id
    assert chapter(a, 'av1', '1', volume='1').logical_chapter_id != chapter(b, 'bv2', '1', volume='2').logical_chapter_id
    assert chapter(a, 'as', 'Side Story 3').logical_chapter_id == chapter(b, 'bs', 'Side Story 3').logical_chapter_id


def test_sync_missing_chapter_preserves_history(context):
    a = work('a', 'a')
    sc = chapter(a, 'ch')
    reader = user()
    save_progress(reader.id, sc, 32, 42)
    sync_chapters(a, [], complete=True)
    db.session.commit()
    assert not sc.available
    assert ReadingProgress.query.one().logical_chapter_id == sc.logical_chapter_id
    assert Readed.query.one().work_id == a.work_id


def test_page_approximation():
    assert approximate_page(32 / 42, 57) == 43
    assert approximate_page(0, 57) == 1
    assert approximate_page(1, 57) == 57


def test_removed_source_resume_and_route(app, monkeypatch):
    with app.app_context():
        a, b = work('a', 'a'), work('b', 'b')
        ca, cb = chapter(a, 'a50'), chapter(b, 'b50')
        reader = user()
        save_progress(reader.id, ca, 32, 42)
        a.available = False
        db.session.commit()
        monkeypatch.setattr(Library, 'sources', staticmethod(lambda: {'b': 'B'}))
        monkeypatch.setattr(Library, 'selected_source', classmethod(lambda cls: 'b'))
        monkeypatch.setattr(Library, '_source_manga', lambda self, id: {'id': id, 'title': 'Solo Leveling',
            'source_id': 'b', 'chapters': [{'cap_id': 'b50', 'cap': '50', 'language': 'en'}]})
        monkeypatch.setattr(Library, '_source_chapter', lambda self, id: {'id': id, 'manga_id': 'b',
            'manga': 'Solo Leveling', 'cap': '50', 'source_id': 'b', 'pages': ['page'] * 57})
        chosen, page = resolve_source_for_chapter(reader.id, a.work, Library())
        assert chosen.id == cb.id and page == 43
        assert ReadingProgress.query.one().logical_chapter_id == cb.logical_chapter_id
        assert Readed.query.one().chapter.uuid == 'a50'
        client = app.test_client()
        with client.session_transaction() as session:
            session['_user_id'] = str(reader.id)
            session['_fresh'] = True
        response = client.get('/work/' + a.work_id + '/continue')
        assert response.status_code == 302 and response.location == '/cap/b50?page=43'
        response = client.post('/cap/b50/progress', json={'page': 43, 'page_count': 57})
        assert response.status_code == 200
        assert ReadingProgress.query.count() == 1
        assert ReadingProgress.query.one().last_source == 'b'
        assert Readed.query.count() == 2



def test_favorites_shared_and_history_backfill(context):
    a, b = work('a', 'a'), work('b', 'b')
    reader = user()
    assert toggle_favorite(reader.id, a) == 'added'
    assert Favorite.query.one().work_id == b.work_id
    assert toggle_favorite(reader.id, b) == 'deleted'
    assert Favorite.query.count() == 0


def test_unavailable_all_preserves_progress(context, monkeypatch):
    a = work('a', 'a')
    reader = user()
    save_progress(reader.id, chapter(a, 'ch'), 32, 42)
    monkeypatch.setattr(Library, 'sources', staticmethod(lambda: {}))
    with pytest.raises(SourceUnavailable, match='preserved'):
        resolve_source_for_chapter(reader.id, a.work, Library())
    assert ReadingProgress.query.one().page_number == 32


def test_offline_legacy_backfill_enrichment_and_repeat(context):
    reader = user()
    old = Manga(uuid='old', title='Legacy')
    db.session.add(old)
    db.session.flush()
    ch = Chapter(uuid='old-chapter', manga_id=old.id)
    db.session.add(ch)
    db.session.flush()
    db.session.add_all([Favorite(user_id=reader.id, manga_id=old.id), Readed(user_id=reader.id, chapter_id=ch.id)])
    db.session.commit()
    backfill()
    db.session.commit()
    work_id = Favorite.query.one().work_id
    assert work_id and Readed.query.one().work_id == work_id
    unknown = ReadingProgress.query.one().logical_chapter_id
    assert 'special:' in db.session.get(LogicalChapter, unknown).chapter_key
    backfill()
    db.session.commit()
    assert Work.query.count() == 1 and ReadingProgress.query.count() == 1
    assert Favorite.query.count() == 1 and Readed.query.count() == 1
    sw = db.session.get(SourceWork, 'old')
    new = chapter(sw, 'old-chapter', '50')
    assert ReadingProgress.query.one().logical_chapter_id == new.logical_chapter_id != unknown


def test_migration_old_schema_roundtrip(app):
    from sqlalchemy import text
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    spec = importlib.util.spec_from_file_location('canonical_migration', 'migrations/versions/20260928_canonical_reading.py')
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with app.app_context():
        db.drop_all()
        with db.engine.begin() as connection:
            for statement in [
                'CREATE TABLE user (id INTEGER PRIMARY KEY, username VARCHAR(100), email VARCHAR(100), password_hash VARCHAR(128))',
                'CREATE TABLE manga (id INTEGER PRIMARY KEY, uuid VARCHAR(36), title VARCHAR(255))',
                'CREATE TABLE chapter (id INTEGER PRIMARY KEY, uuid VARCHAR(36), manga_id INTEGER)',
                'CREATE TABLE favorite (id INTEGER PRIMARY KEY, user_id INTEGER, manga_id INTEGER, chapter_id INTEGER)',
                'CREATE TABLE readed (id INTEGER PRIMARY KEY, user_id INTEGER, chapter_id INTEGER, created_at DATETIME, updated_at DATETIME)',
                'CREATE TABLE source_reference (id VARCHAR(36) PRIMARY KEY, source VARCHAR(32), kind VARCHAR(16), remote_id TEXT, parent_id VARCHAR(36), payload JSON)',
                "INSERT INTO user VALUES (1, 'reader', 'test@example.test', 'unused')",
                "INSERT INTO manga VALUES (1, 'legacy', 'Preserved')",
                "INSERT INTO chapter VALUES (1, 'legacy-ch', 1)",
                'INSERT INTO favorite VALUES (1, 1, 1, NULL)',
                "INSERT INTO readed VALUES (1, 1, 1, '2020-01-01 00:00:00', '2020-01-02 00:00:00')",
            ]:
                connection.execute(text(statement))
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
                migration.downgrade()
                migration.upgrade()
        assert Work.query.count() == 1
        assert ReadingProgress.query.one().work_id == Favorite.query.one().work_id
        assert Readed.query.one().chapter_id == 1
        assert Manga.query.one().uuid == 'legacy'


def test_enrichment_then_backfill_does_not_erase_number_or_progress(context):
    reader = user()
    sw = work('mangadex', 'old')
    sc = chapter(sw, 'old-chapter', '50')
    progress = save_progress(reader.id, sc, 32, 42)
    backfill()
    db.session.commit()
    assert progress.logical_chapter.label == '50'
    assert progress.page_number == 32
    assert progress.progress_percent == 32 / 42


def test_duplicate_releases_stay_ambiguous_after_opening(context):
    sw = work('a', 'a')
    rows = sync_chapters(sw, [{'cap_id': 'x', 'cap': '1', 'language': 'en'},
                             {'cap_id': 'y', 'cap': '1', 'language': 'en'}], complete=True)
    db.session.commit()
    original = rows[0].logical_chapter_id
    assert rows[0].logical_chapter_id != rows[1].logical_chapter_id
    assert chapter(sw, 'x', '1').logical_chapter_id == original


def test_progress_endpoint_login_csrf_and_private_api(app):
    with app.app_context():
        sw = work('a', 'a')
        chapter(sw, 'ch')
        reader = user()
        work_id, reader_id = sw.work_id, reader.id
    client = app.test_client()
    assert client.post('/cap/ch/progress', json={'page': 1, 'page_count': 3}).status_code == 302
    with client.session_transaction() as session:
        session['_user_id'] = str(reader_id)
        session['_fresh'] = True
    assert client.post('/cap/ch/progress', json={'page': 4, 'page_count': 3}).status_code == 400
    assert client.post('/cap/ch/progress', json={'page': True, 'page_count': 3}).status_code == 400
    app.config['WTF_CSRF_ENABLED'] = True
    assert client.post('/cap/ch/progress', json={'page': 1, 'page_count': 3}).status_code == 400
    app.config['WTF_CSRF_ENABLED'] = False
    assert client.post('/cap/ch/progress', json={'page': 1, 'page_count': 3}).status_code == 200
    response = client.get('/api/works/' + work_id)
    assert response.json['reading_progress']['progress_percent'] == 1 / 3
    assert response.headers['Cache-Control'] == 'private, no-store'
    anonymous = app.test_client().get('/api/works/' + work_id)
    assert anonymous.json['reading_progress'] is None


def test_plan_to_read_before_first_chapter(app):
    with app.app_context():
        sw = work('a', 'a')
        reader = user()
        work_id, reader_id = sw.work_id, reader.id
    client = app.test_client()
    with client.session_transaction() as session:
        session['_user_id'] = str(reader_id)
        session['_fresh'] = True
    response = client.post('/work/' + work_id + '/status', json={'status': 'plan_to_read'})
    assert response.status_code == 200
    assert 'Plan to read' in client.get('/biblioteca').text
    with app.app_context():
        row = ReadingProgress.query.one()
        assert row.work_id == work_id and row.logical_chapter_id is None


def test_late_alias_merge_preserves_both_histories(context):
    a, b = work('a', 'a', 'Original'), work('b', 'b', 'Translation')
    ca, cb = chapter(a, 'ca'), chapter(b, 'cb')
    reader = user()
    save_progress(reader.id, ca, 5, 10)
    save_progress(reader.id, cb, 7, 10)
    original_b = b.work_id
    b = work('b', 'b', 'Translation', aliases=['Original'])
    assert a.work_id == b.work_id
    assert ReadingProgress.query.count() == 1
    assert ReadingProgress.query.one().page_number == 7
    assert {r.work_id for r in Readed.query.all()} == {a.work_id}
    assert len({r.logical_chapter_id for r in Readed.query.all()}) == 1
    from app.libs.canonical import canonical_work
    assert canonical_work(original_b).id == a.work_id


def test_rotated_source_repairs_existing_duplicates_and_history(context):
    from app.libs.identity import fingerprint
    from app.libs.canonical import canonical_work
    # Simulate rows created before URL-token rotations were recognized.
    a, b = work('asura', 'old'), work('asura', 'new')
    old_work_id = a.work_id
    for row, token in ((a, '05c7df14'), (b, '3ec3b16f')):
        row.external_id = 'comics/solo-leveling-' + token
        row.external_hash = fingerprint(row.external_id)
    ca, cb = chapter(a, 'old50'), chapter(b, 'new50')
    reader = user()
    save_progress(reader.id, ca, 32, 42)
    save_progress(reader.id, cb, 43, 57)
    for _ in range(2):
        resolved = work('asura', 'new', external_id=b.external_id)
        assert a.work_id == resolved.work_id
        assert canonical_work(old_work_id).id == resolved.work_id
        assert ReadingProgress.query.count() == 1
        assert ReadingProgress.query.one().page_number == 43
        assert {r.work_id for r in Readed.query.all()} == {resolved.work_id}
        assert len({r.logical_chapter_id for r in Readed.query.all()}) == 1
        assert SourceWork.query.count() == 2
    other = work('qiscans', 'qi')
    assert other.work_id == resolved.work_id


@pytest.mark.parametrize('source,remote,extra', [
    ('asura', 'comics/solo-leveling-2-3ec3b16f', {}),
    ('asura', 'comics/solo-leveling-remake-3ec3b16f', {}),
    ('asura', 'comics/solo-leveling-3ec3b16f', {'type': 'novel'}),
    ('qiscans', 'solo-leveling-2', {}),
])
def test_url_identity_does_not_merge_editions(context, source, remote, extra):
    first = 'comics/solo-leveling-05c7df14' if source == 'asura' else 'solo-leveling'
    a = work(source, 'a', external_id=first, type='manga')
    b = work(source, 'b', external_id=remote, **extra)
    assert a.work_id != b.work_id


def test_rotated_url_respects_conflicting_external_ids(context):
    a = work('asura', 'a', external_id='comics/solo-leveling-05c7df14',
             external_ids={'anilist': '1'})
    b = work('asura', 'b', external_id='comics/solo-leveling-3ec3b16f',
             external_ids={'anilist': '2'})
    assert a.work_id != b.work_id


def test_provider_failure_falls_back_without_premarking(context, monkeypatch):
    a, b = work('a', 'a'), work('b', 'b')
    reader = user()
    ca, cb = chapter(a, 'a50'), chapter(b, 'b50')
    save_progress(reader.id, ca, 32, 42)
    monkeypatch.setattr(Library, 'sources', staticmethod(lambda: {'a': 'A', 'b': 'B'}))
    def details(self, identifier):
        if identifier == 'a':
            raise SourceUnavailable('offline')
        return {'id': 'b', 'title': 'Solo Leveling', 'source_id': 'b',
                'chapters': [{'cap_id': 'b50', 'cap': '50', 'language': 'en'}]}
    monkeypatch.setattr(Library, '_source_manga', details)
    monkeypatch.setattr(Library, '_source_chapter', lambda *args: {'id': 'b50', 'manga_id': 'b',
        'manga': 'Solo Leveling', 'source_id': 'b', 'cap': '50', 'pages': ['page'] * 57})
    chosen, page = resolve_source_for_chapter(reader.id, a.work, Library())
    assert chosen.id == 'b50' and page == 43
    assert not a.available
    assert Readed.query.one().chapter.uuid == 'a50'


def test_partial_read_is_not_a_completed_chapter(context):
    reader = user()
    sw = work('a', 'a')
    sc = chapter(sw, 'ch')
    save_progress(reader.id, sc, 2, 10)
    assert not Readed.query.one().completed
    save_progress(reader.id, sc, 10, 10, completed=True)
    assert Readed.query.one().completed


def test_volume_enrichment_preserves_only_relevant_progress(context):
    a, b = work('a', 'a'), work('b', 'b')
    ca, cb = chapter(a, 'ca', '12'), chapter(b, 'cb', '12')
    reader = user()
    save_progress(reader.id, ca, 2, 10)
    old = cb.logical_chapter_id
    new = chapter(a, 'ca', '12', volume='2')
    assert ReadingProgress.query.one().logical_chapter_id == new.logical_chapter_id
    assert cb.logical_chapter_id == old != new.logical_chapter_id


def test_canonical_page_survives_all_sources_removed(app, monkeypatch):
    with app.app_context():
        a = work('asura', 'a')
        reader = user()
        save_progress(reader.id, chapter(a, 'ca'), 32, 42)
        work_id, reader_id = a.work_id, reader.id
    monkeypatch.setattr(Library, 'sources', staticmethod(lambda: {'mangadex': 'MangaDex'}))
    client = app.test_client()
    with client.session_transaction() as session:
        session['_user_id'] = str(reader_id)
        session['_fresh'] = True
    response = client.get('/work/' + work_id)
    assert response.status_code == 200
    assert 'Continue reading' in response.text and 'chapter 50' in response.text
    assert 'asura — unavailable' in response.text


def test_worker_unread_state_is_shared_across_sources(app, monkeypatch):
    from app.update_worker import refresh_once
    from app.models import UpdateNotification
    with app.app_context():
        a, b = work('a', 'a'), work('b', 'b')
        ca, cb = chapter(a, 'a50'), chapter(b, 'b50')
        reader = user()
        save_progress(reader.id, ca, 42, 42, completed=True)
        toggle_favorite(reader.id, b)
        monkeypatch.setattr(Library, 'work_details', lambda *args: {'title': 'Solo Leveling',
            'chapters': [{'cap_id': cb.id, 'cap': '50'}], 'source_name': 'B'})
        assert refresh_once() == 0
        assert UpdateNotification.query.count() == 0


def test_resynchronizing_many_chapters_uses_bounded_reads(context):
    from sqlalchemy import event
    sw = work('a', 'a')
    entries = [{'cap_id': 'chapter-' + str(i), 'cap': str(i), 'language': 'en'} for i in range(100)]
    sync_chapters(sw, entries, complete=True)
    db.session.commit()
    reads = []
    def record(connection, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith('SELECT'):
            reads.append(statement)
    event.listen(db.engine, 'before_cursor_execute', record)
    try:
        sync_chapters(sw, entries, complete=True)
        db.session.commit()
    finally:
        event.remove(db.engine, 'before_cursor_execute', record)
    assert len(reads) < 12
    assert SourceChapter.query.count() == 100
    assert LogicalChapter.query.count() == 100


def test_alias_consolidation_during_resume_uses_surviving_progress(context, monkeypatch):
    a, b = work('a', 'a', 'Original'), work('b', 'b', 'Translation')
    ca, cb = chapter(a, 'ca'), chapter(b, 'cb')
    reader = user()
    save_progress(reader.id, ca, 5, 10)
    save_progress(reader.id, cb, 7, 10)
    monkeypatch.setattr(Library, 'sources', staticmethod(lambda: {'a': 'A'}))
    monkeypatch.setattr(Library, '_source_manga', lambda *args: {'id': 'a', 'title': 'Original',
        'aliases': ['Translation'], 'source_id': 'a', 'chapters': [{'cap_id': 'ca', 'cap': '50', 'language': 'en'}]})
    monkeypatch.setattr(Library, '_source_chapter', lambda *args: {'id': 'ca', 'manga_id': 'a',
        'manga': 'Original', 'source_id': 'a', 'cap': '50', 'pages': ['page'] * 10})
    selected, page = resolve_source_for_chapter(reader.id, a.work, Library())
    assert selected.id == 'ca' and page == 7
    assert ReadingProgress.query.count() == 1
    assert Readed.query.count() == 2
