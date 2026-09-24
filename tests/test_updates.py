from app import db
from app.models import Favorite, Manga, User, UpdateNotification, utc_now
from app.update_worker import refresh_once


def test_refresh_once_creates_and_deduplicates_notification(app, monkeypatch):
    with app.app_context():
        user = User(username='updates', email='updates@example.com', password_hash='unused')
        manga = Manga(uuid='manga-updates', title='Story')
        db.session.add_all([user, manga])
        db.session.flush()
        db.session.add(Favorite(user_id=user.id, manga_id=manga.id))
        db.session.commit()

        monkeypatch.setattr('app.update_worker.Library.showManga', lambda *_: {
            'title': 'Story', 'source_name': 'MangaDex',
            'chapters': [{'cap_id': 'chapter-2', 'cap': '2'}, {'cap_id': 'chapter-1', 'cap': '1'}],
        })
        assert refresh_once() == 1
        assert refresh_once() == 0
        entry = UpdateNotification.query.one()
        assert (entry.chapter_uuid, entry.chapter_label) == ('chapter-2', '2')


def test_refresh_once_ignores_read_chapters(app, monkeypatch):
    with app.app_context():
        user = User(username='read-updates', email='read-updates@example.com', password_hash='unused')
        manga = Manga(uuid='manga-read-updates', title='Story')
        db.session.add_all([user, manga])
        db.session.flush()
        db.session.add(Favorite(user_id=user.id, manga_id=manga.id))
        db.session.commit()

        monkeypatch.setattr('app.update_worker.Library.showManga', lambda *_: {
            'title': 'Story', 'source_name': 'AsuraScans',
            'chapters': [{'cap_id': 'chapter-read', 'cap': '4'}],
        })
        from app.models import Chapter, Readed
        chapter = Chapter(uuid='chapter-read', manga_id=manga.id)
        db.session.add(chapter)
        db.session.flush()
        db.session.add(Readed(user_id=user.id, chapter_id=chapter.id,
                              created_at=utc_now(), updated_at=utc_now()))
        db.session.commit()
        assert refresh_once() == 0
        assert UpdateNotification.query.count() == 0


def test_notification_constraint_is_unique_per_user_and_chapter(app):
    with app.app_context():
        user = User(username='unique-updates', email='unique-updates@example.com', password_hash='unused')
        db.session.add(user)
        db.session.commit()
        db.session.add_all([
            UpdateNotification(user_id=user.id, manga_uuid='m1', manga_title='Story', chapter_uuid='c1', chapter_label='1', source_name='MangaDex'),
            UpdateNotification(user_id=user.id, manga_uuid='m1', manga_title='Story', chapter_uuid='c1', chapter_label='1', source_name='MangaDex'),
        ])
        import pytest
        with pytest.raises(Exception):
            db.session.commit()
        db.session.rollback()
