"""Canonical progress and provider selection; no persistent image storage."""
from flask import current_app
from app import db
from app.models import (SourceChapter, ReadingProgress, Readed, Chapter,
                        Favorite, utc_now)
from app.libs.canonical import lock_catalog, ensure_legacy_manga, canonical_work
from app.libs.identity import approximate_page
from app.libs.manga_novel import SourceUnavailable
import requests
from mangadex.errors import ApiError

PROVIDER_ERRORS = (SourceUnavailable, requests.RequestException, ApiError)
STATUSES = {'reading', 'plan_to_read', 'completed', 'paused', 'dropped'}


def save_progress(user_id, source_chapter, page, count, *, completed=False):
    lock_catalog()
    sw = source_chapter.source_work
    manga = ensure_legacy_manga(sw)
    chapter = Chapter.query.filter_by(uuid=source_chapter.id).first()
    if chapter is None:
        chapter = Chapter(uuid=source_chapter.id, manga_id=manga.id)
        db.session.add(chapter)
        db.session.flush()
    now = utc_now()
    percent = page / count if count else (1.0 if completed else 0.0)
    read = Readed.query.filter_by(user_id=user_id, chapter_id=chapter.id).first()
    if read is None:
        read = Readed(user_id=user_id, chapter_id=chapter.id, completed=False)
        db.session.add(read)
    read.work_id, read.logical_chapter_id = sw.work_id, source_chapter.logical_chapter_id
    read.page_number, read.page_count, read.progress_percent = page, count, percent
    read.completed = bool(read.completed or completed)
    read.updated_at = now
    progress = ReadingProgress.query.filter_by(user_id=user_id, work_id=sw.work_id).first()
    if progress is None:
        progress = ReadingProgress(user_id=user_id, work_id=sw.work_id)
        db.session.add(progress)
    progress.logical_chapter_id = source_chapter.logical_chapter_id
    progress.page_number, progress.page_count, progress.progress_percent = page, count, percent
    progress.last_source, progress.last_source_chapter_id = sw.source, source_chapter.id
    progress.last_read_at = now
    progress.completed_at = now if completed else None
    progress.status = 'reading'
    db.session.commit()
    return progress


def source_order(work, library, progress=None):
    configured = library.sources()
    priority = current_app.config.get('SOURCE_PRIORITY', list(configured))
    return sorted((s for s in work.sources if s.source in configured), key=lambda s: (
        not s.available,
        s.source != (progress.last_source if progress else None),
        priority.index(s.source) if s.source in priority else len(priority), s.id))


def resolve_source_for_chapter(user_id, work, library, *, discover=True, _attempted=None):
    attempted = set() if _attempted is None else _attempted
    progress = ReadingProgress.query.filter_by(user_id=user_id, work_id=work.id).first()
    if progress is None or progress.logical_chapter_id is None:
        raise SourceUnavailable('This work has no saved progress yet. Choose a chapter to start reading.')
    # Try known chapter mappings first; discovery should not delay a working source.
    work = canonical_work(work.id)
    progress = ReadingProgress.query.filter_by(user_id=user_id, work_id=work.id).one()
    sources = source_order(work, library, progress)
    for sw in sources:
        if sw.id in attempted:
            continue
        attempted.add(sw.id)
        try:
            # Refresh the chapter mapping. A failed source is retained, not deleted.
            library.showManga(sw.id)
            # Enriched aliases can consolidate two works and replace the
            # progress row while a provider's details are being loaded.
            work = canonical_work(work.id)
            progress = ReadingProgress.query.filter_by(user_id=user_id, work_id=work.id).one()
            target_id = progress.logical_chapter_id
            candidates = SourceChapter.query.filter_by(source_work_id=sw.id,
                                                       logical_chapter_id=target_id, available=True).all()
            previous = db.session.get(SourceChapter, progress.last_source_chapter_id) if progress.last_source_chapter_id else None
            candidates.sort(key=lambda c: (c.id != progress.last_source_chapter_id,
                                            c.language != (previous.language if previous else None),
                                            c.language not in ('pt-br', 'pt'), c.id))
            for candidate in candidates:
                try:
                    data = library.getChapter(candidate.id)
                    count = len(data.get('pages', []))
                    if not count:
                        candidate.available = False
                        db.session.commit()
                        continue
                    page = (min(max(1, progress.page_number), count)
                            if candidate.id == progress.last_source_chapter_id
                            else approximate_page(progress.progress_percent, count))
                    return candidate, page
                except PROVIDER_ERRORS:
                    candidate.available = False
                    db.session.commit()
        except PROVIDER_ERRORS:
            sw.available = False
            db.session.commit()
    if discover:
        library.discover_work_sources(work)
        return resolve_source_for_chapter(user_id, canonical_work(work.id), library,
                                          discover=False, _attempted=attempted)
    raise SourceUnavailable('Your progress has been preserved. No available source has this chapter right now.')


def toggle_favorite(user_id, sw):
    lock_catalog()
    rows = Favorite.query.filter_by(user_id=user_id, work_id=sw.work_id).all()
    if rows:
        for row in rows:
            db.session.delete(row)
        status = 'deleted'
    else:
        manga = ensure_legacy_manga(sw)
        # Adopt legacy rows lazily for tests/imports made after the schema migration.
        legacy = Favorite.query.filter_by(user_id=user_id, manga_id=manga.id).first()
        if legacy:
            db.session.delete(legacy)
            status = 'deleted'
        else:
            db.session.add(Favorite(user_id=user_id, manga_id=manga.id, work_id=sw.work_id))
            status = 'added'
    db.session.commit()
    return status
