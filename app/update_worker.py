"""Background updater for unread chapters in user favorites."""
import os
import time
from datetime import timedelta

from flask import current_app

from app import create_app, db
from app.libs.library import Library
from app.models import Favorite, Readed, Chapter, UpdateNotification, WorkerStatus, SourceChapter, utc_now
from sqlalchemy.exc import IntegrityError


def refresh_once(user_id=None):
    library = Library()
    created = 0
    query = Favorite.query.order_by(Favorite.id.asc())
    if user_id is not None:
        query = query.filter_by(user_id=user_id)
    favorites = query.all()
    if user_id is None:
        UpdateNotification.query.filter(
            UpdateNotification.read_at.isnot(None),
            UpdateNotification.created_at < utc_now() - timedelta(days=90),
        ).delete(synchronize_session=False)
    visited = set()
    for favorite in favorites:
        key = (favorite.user_id, favorite.work_id or favorite.manga.uuid)
        if key in visited:
            continue
        visited.add(key)
        try:
            details = library.work_details(favorite.work) if favorite.work else library.showManga(favorite.manga.uuid)
            chapters = details.get('chapters', [])
            if not chapters:
                continue
            unread = []
            for chapter in chapters:
                chapter_id = chapter.get('cap_id')
                if not chapter_id:
                    continue
                already_read = db.session.query(Readed.id).join(Chapter).filter(
                    Readed.user_id == favorite.user_id, Readed.completed.is_(True), Chapter.uuid == chapter_id).first()
                mapped = db.session.get(SourceChapter, chapter_id)
                if mapped and not already_read:
                    already_read = Readed.query.filter_by(user_id=favorite.user_id, logical_chapter_id=mapped.logical_chapter_id, completed=True).first()
                if not already_read:
                    unread.append(chapter)
            if not unread:
                continue
            latest = unread[0]
            from app.libs.canonical import lock_catalog
            lock_catalog()
            exists = UpdateNotification.query.filter_by(
                user_id=favorite.user_id, chapter_uuid=latest['cap_id']).first()
            mapped = db.session.get(SourceChapter, latest['cap_id'])
            if mapped and not exists:
                exists = UpdateNotification.query.filter_by(
                    user_id=favorite.user_id, logical_chapter_id=mapped.logical_chapter_id).first()
            if exists:
                db.session.commit()
                continue
            db.session.add(UpdateNotification(
                user_id=favorite.user_id,
                work_id=mapped.source_work.work_id if mapped else favorite.work_id,
                logical_chapter_id=mapped.logical_chapter_id if mapped else None,
                manga_uuid=favorite.manga.uuid,
                manga_title=details.get('title', favorite.manga.title),
                chapter_uuid=latest['cap_id'],
                chapter_label=str(latest.get('cap', 'Sem número')),
                source_name=details.get('source_name', 'MangaDex'),
            ))
            # Commit each notification independently so one broken provider
            # cannot roll back updates already collected for other favorites.
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                # Another worker won the race to create this notification.
                continue
            created += 1
        except Exception:
            db.session.rollback()
    db.session.commit()
    return created


def main():
    app = create_app()
    interval = max(300, int(os.getenv('UPDATES_INTERVAL_SECONDS', '1800')))
    with app.app_context():
        while True:
            status = db.session.get(WorkerStatus, 1)
            if status is None:
                status = WorkerStatus(id=1)
                db.session.add(status)
                db.session.commit()
            status.last_run_at = utc_now()
            try:
                created = refresh_once()
                status.last_success_at = utc_now()
                status.last_created = created
                status.last_error = None
                db.session.commit()
                current_app.logger.info('Update worker: %s notifications created', created)
            except Exception as error:
                status.last_error = str(error)[:1000]
                db.session.commit()
                current_app.logger.exception('Update worker iteration failed')
            time.sleep(interval)


if __name__ == '__main__':
    main()
