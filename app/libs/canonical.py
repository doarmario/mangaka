"""Local catalog authority. Providers supply metadata; identity lives here."""
import logging
from uuid import uuid4
from sqlalchemy import update, inspect
from app import db
from app.models import (CatalogLock, Work, WorkAlias, WorkExternalID, SourceWork,
                        LogicalChapter, SourceChapter, Manga, Chapter, Favorite,
                        Readed, ReadingProgress, SourceReference, UpdateNotification, utc_now)
from app.libs.identity import (normalize_title, title_keys, fingerprint, metadata,
                               compatible, chapter_identity, match_confidence, title_variants,
                               source_work_key)

log = logging.getLogger(__name__)


def lock_catalog():
    # A single atomic upsert avoids the shared-lock -> exclusive-lock upgrade
    # deadlock when several workers initialize the mutex at the same time.
    if db.session.get_bind().dialect.name == 'mysql':
        from sqlalchemy.dialects.mysql import insert
        statement = insert(CatalogLock).values(id=1, version=1)
        db.session.execute(statement.on_duplicate_key_update(version=CatalogLock.version + 1))
    else:
        from sqlalchemy.dialects.sqlite import insert
        statement = insert(CatalogLock).values(id=1, version=1)
        db.session.execute(statement.on_conflict_do_update(index_elements=['id'], set_={'version': CatalogLock.version + 1}))


def work_data(work):
    return {'title': work.canonical_title, 'aliases': [a.alias for a in work.aliases], **work.metadata_json}


def _aliases(work, item, source):
    variants = title_variants(item, source)
    # Keep raw spellings and language/source provenance separately from the
    # deduplicated matching index. Punctuation/case variants must not be lost.
    work.metadata_json = {**work.metadata_json, 'titles': title_variants({
        'titles': [*work.metadata_json.get('titles', []), *variants]})}
    existing = {a.alias_hash for a in work.aliases}
    keys = title_keys(item)
    for entry in variants:
        value = entry['title']
        if normalize_title(value) not in keys:
            continue
        normalized = normalize_title(value)
        digest = fingerprint(normalized)
        if digest not in existing:
            db.session.add(WorkAlias(work=work, alias=value, normalized_alias=normalized,
                                     alias_hash=digest, origin=source))
            existing.add(digest)


def _merge_compatible(left, right):
    if not compatible(work_data(left), work_data(right)):
        return False
    for a in left.sources:
        for b in right.sources:
            if a.source == b.source and source_work_key(a.source, a.external_id) != source_work_key(b.source, b.external_id):
                return False
    left_ids = {r.provider: r.external_id for r in WorkExternalID.query.filter_by(work_id=left.id)}
    right_ids = {r.provider: r.external_id for r in WorkExternalID.query.filter_by(work_id=right.id)}
    return all(left_ids[p] == right_ids[p] for p in left_ids.keys() & right_ids.keys())


def _rotated_source_work(item, source, remote, known):
    """Repair verified URL-token rotations while retaining old source records."""
    key = source_work_key(source, remote)
    if key == remote:
        return known.work if known else None
    records = SourceWork.query.filter_by(source=source).filter(
        SourceWork.external_id.startswith(key + '-', autoescape=True)).all()
    works = {row.work_id: row.work for row in records
             if source_work_key(source, row.external_id) == key}
    if not works:
        return None
    candidates = list(works.values())
    incoming_ids = {str(p): str(v) for p, v in (item.get('external_ids') or {}).items() if v}
    if (not all(match_confidence(work_data(w), item)[0] == 1.0 for w in candidates)
            or any(r.provider in incoming_ids and incoming_ids[r.provider] != r.external_id
                   for w in candidates for r in WorkExternalID.query.filter_by(work_id=w.id))
            or not all(_merge_compatible(a, b) for i, a in enumerate(candidates) for b in candidates[i + 1:])):
        return known.work if known else None
    target = known.work if known else candidates[0]
    for old in candidates:
        if old.id != target.id:
            merge_works(target, old)
            db.session.expire(target, ['sources', 'aliases'])
            db.session.expire(old, ['sources', 'aliases'])
            log.debug('Consolidated rotated %s source URL: work %s -> %s', source, old.id, target.id)
    return target


def resolve_work(item, source, *, allow_title_match=True):
    """Resolve under the catalog lock. Caller commits before doing any HTTP."""
    lock_catalog()
    identifier = str(item['id'])
    ref = db.session.get(SourceReference, identifier)
    remote = ref.remote_id if ref else str(item.get('external_id') or identifier)
    external = {str(k): str(v) for k, v in (item.get('external_ids') or {}).items()
                if v and len(str(k)) <= 32 and len(str(v)) <= 255}
    if source == 'mangadex':
        external['mangadex'] = remote
    known = db.session.get(SourceWork, identifier)
    if known is None:
        known = SourceWork.query.filter_by(source=source, external_hash=fingerprint(remote)).first()
    work = _rotated_source_work(item, source, remote, known)
    strong = {r.work_id for p, v in external.items() for r in
              WorkExternalID.query.filter_by(provider=p, external_id=v).all()}
    reason = 'source_mapping' if known else ''
    if len(strong) == 1:
        target = db.session.get(Work, next(iter(strong)))
        if work is None:
            work, reason = target, 'external_id'
        elif target.id != work.id:
            log.warning('Conflicting external identity for source work %s; mapping preserved', identifier)
    elif len(strong) > 1:
        log.warning('Ambiguous external identities for source work %s', identifier)
        allow_title_match = False
    keys = title_keys(item)
    candidates = []
    if keys and allow_title_match and (not strong or (work and strong == {work.id})):
        rows = Work.query.join(WorkAlias).filter(WorkAlias.alias_hash.in_([fingerprint(k) for k in keys])).distinct().all()
        candidates = [w for w in rows if not w.metadata_json.get('redirect_to') and (work is None or w.id != work.id)
                      and compatible(work_data(w), item)
                      and not any(s.source == source and s.id != identifier for s in w.sources)]
        if len(candidates) == 1:
            if work is None:
                work, reason = candidates[0], 'exact_alias'
            elif _merge_compatible(work, candidates[0]):
                work = merge_works(candidates[0], work)
                db.session.expire(work, ['sources', 'aliases'])
                reason = 'exact_alias'
        elif len(candidates) > 1:
            log.debug('Ambiguous match rejected for source work %s', identifier)
    if work is None:
        work = Work(canonical_title=str(item.get('title') or 'Sem título')[:255],
                    normalized_title=normalize_title(item.get('title')), metadata_json={**metadata(item), 'match_candidates': matching_candidates(item)},
                    description=item.get('sinopse'))
        db.session.add(work)
        db.session.flush()
        reason = 'new_work'
    work.metadata_json = {**work.metadata_json, **metadata(item)}
    if item.get('sinopse'):
        work.description = item['sinopse']
    _aliases(work, item, source)
    for provider, value in external.items():
        row = WorkExternalID.query.filter_by(provider=provider, external_id=value).first()
        if row is None:
            db.session.add(WorkExternalID(work_id=work.id, provider=provider, external_id=value))
    now = utc_now()
    if known is None:
        known = SourceWork(id=identifier, work_id=work.id, source=source,
                           external_id=remote, external_hash=fingerprint(remote))
        db.session.add(known)
    known.work_id = work.id
    known.title_at_source = str(item.get('title') or work.canonical_title)[:255]
    known.normalized_title = normalize_title(known.title_at_source)
    known.source_url = item.get('source_url') or (ref.payload.get('url') if ref else None)
    known.available = True
    known.last_seen_at = known.last_success_at = now
    db.session.flush()
    log.debug('Resolved source work %s -> %s by %s', identifier, work.id, reason)
    return known


def merge_works(target, old):
    """Conservative identity consolidation; preserve every legacy reading row."""
    for chapter in LogicalChapter.query.filter_by(work_id=old.id).all():
        existing = LogicalChapter.query.filter_by(work_id=target.id, key_hash=chapter.key_hash).first()
        if existing:
            rebind_chapter(chapter, existing)
        else:
            chapter.work_id = target.id
    for row in ReadingProgress.query.filter_by(work_id=old.id).all():
        existing = ReadingProgress.query.filter_by(user_id=row.user_id, work_id=target.id).first()
        if existing:
            if row.last_read_at > existing.last_read_at:
                for field in ('logical_chapter_id', 'page_number', 'page_count', 'progress_percent',
                              'last_source', 'last_source_chapter_id', 'last_read_at', 'completed_at', 'status'):
                    setattr(existing, field, getattr(row, field))
            existing.started_at = min(existing.started_at, row.started_at)
            db.session.delete(row)
        else:
            row.work_id = target.id
    for model in (SourceWork, Favorite, Readed, WorkExternalID, UpdateNotification):
        for row in model.query.filter_by(work_id=old.id).all():
            row.work_id = target.id
    for alias in list(old.aliases):
        _aliases(target, {'title': alias.alias}, alias.origin)
        db.session.delete(alias)
    _aliases(target, {'titles': old.metadata_json.get('titles', [])}, None)
    db.session.flush()
    # Keep a redirect so previously issued canonical URLs remain valid.
    old.metadata_json = {**old.metadata_json, 'redirect_to': target.id}
    return target


def canonical_work(identifier):
    work = db.session.get(Work, identifier)
    seen = set()
    while work and work.metadata_json.get('redirect_to') and work.id not in seen:
        seen.add(work.id)
        work = db.session.get(Work, work.metadata_json['redirect_to'])
    return work


def rebind_chapter(old, new):
    for model in (SourceChapter, Readed, ReadingProgress, UpdateNotification):
        if model is UpdateNotification and not inspect(db.session.connection()).has_table('update_notification'):
            continue
        for row in model.query.filter_by(logical_chapter_id=old.id).all():
            row.logical_chapter_id = new.id
    db.session.flush()
    # Preserve the old logical ID as metadata; no deletion of historical tables.


def sync_chapters(source_work, chapters, *, complete=False):
    lock_catalog()
    now = utc_now()
    result = []
    counts = {}
    existing_rows = {row.id: row for row in SourceChapter.query.filter_by(source_work_id=source_work.id).all()}
    logical_rows = LogicalChapter.query.filter_by(work_id=source_work.work_id).all()
    logical_by_hash = {row.key_hash: row for row in logical_rows}
    logical_by_id = {row.id: row for row in logical_rows}
    references = {row.id: row for row in SourceReference.query.filter(SourceReference.id.in_([str(c['cap_id']) for c in chapters])).all()}
    for data in chapters:
        key = chapter_identity(data.get('cap'), data.get('volume'), data.get('title'), data['cap_id'])[0]
        counts[(key, data.get('language'))] = counts.get((key, data.get('language')), 0) + 1
    for data in chapters:
        identifier = str(data['cap_id'])
        key, label, numeric, volume = chapter_identity(data.get('cap'), data.get('volume'), data.get('title'), identifier)
        # Same-language duplicate numbers are ambiguous releases, not proof of equivalence.
        if counts[(key, data.get('language'))] > 1:
            key += '|release:' + identifier
        previous = existing_rows.get(identifier)
        if previous and not complete and '|release:' in logical_by_id[previous.logical_chapter_id].chapter_key:
            key = logical_by_id[previous.logical_chapter_id].chapter_key
        digest = fingerprint(key)
        logical = logical_by_hash.get(digest)
        if logical is None:
            logical = LogicalChapter(id=str(uuid4()), work_id=source_work.work_id, chapter_key=key, key_hash=digest,
                                     label=label[:255], chapter_number=numeric, volume_number=volume[:80], title=data.get('title'))
            db.session.add(logical)
            logical_by_hash[digest] = logical
            logical_by_id[logical.id] = logical
        row = previous
        ref = references.get(identifier)
        remote = ref.remote_id if ref else identifier
        if row is None:
            row = SourceChapter(id=identifier, source_work_id=source_work.id,
                                external_id=remote, external_hash=fingerprint(remote), logical_chapter_id=logical.id)
            db.session.add(row)
        elif row.logical_chapter_id != logical.id:
            # Enrich an unknown migrated chapter once its provider reveals its number.
            old = logical_by_id[row.logical_chapter_id]
            if old.chapter_key.startswith('v:|c:special:'):
                rebind_chapter(old, logical)
            else:
                # Correct/enrich only the history of this release. Other sources
                # sharing its former number may genuinely represent that chapter.
                for read in Readed.query.join(Chapter).filter(Chapter.uuid == row.id).all():
                    read.logical_chapter_id = logical.id
                for progress in ReadingProgress.query.filter_by(last_source_chapter_id=row.id).all():
                    progress.logical_chapter_id = logical.id
                if inspect(db.session.connection()).has_table('update_notification'):
                    for notice in UpdateNotification.query.filter_by(chapter_uuid=row.id).all():
                        notice.logical_chapter_id = logical.id
            row.logical_chapter_id = logical.id
        row.logical_chapter = logical
        row.number_at_source = str(data.get('cap') if data.get('cap') is not None else '')[:255]
        row.language = data.get('language')
        row.title = data.get('title')
        row.source_url = data.get('source_url')
        row.available = True
        row.last_seen_at = row.last_success_at = now
        result.append(row)
    if complete:
        ids = {r.id for r in result}
        for missing in existing_rows.values():
            if missing.id not in ids:
                missing.available = False
                log.debug('Source chapter %s marked unavailable', missing.id)
    source_work.available = True
    source_work.last_seen_at = source_work.last_success_at = now
    db.session.flush()
    return result


def ensure_legacy_manga(source_work):
    row = Manga.query.filter_by(uuid=source_work.id).first()
    if row is None:
        row = Manga(uuid=source_work.id, title=source_work.title_at_source)
        db.session.add(row)
        db.session.flush()
    return row


def backfill():
    """Offline, repeatable migration; unknown chapter numbers remain explicit."""
    from sqlalchemy import inspect
    references = SourceReference.query.filter_by(kind='manga').all()
    for ref in references:
        if db.session.get(SourceWork, ref.id) is not None:
            continue
        item = {**ref.payload, 'id': ref.id, 'title': ref.payload.get('title') or 'Sem título'}
        ambiguous = any(other.id != ref.id and other.source == ref.source
                        and title_keys(other.payload) & title_keys(item) for other in references)
        sw = resolve_work(item, ref.source, allow_title_match=not ambiguous)
        sw.last_seen_at = sw.last_success_at = None
    for manga in Manga.query.order_by(Manga.id).all():
        ref = db.session.get(SourceReference, manga.uuid)
        payload = ref.payload if ref else {}
        sw = db.session.get(SourceWork, manga.uuid) or resolve_work({**payload, 'id': manga.uuid, 'title': manga.title}, ref.source if ref else 'mangadex')
        for favorite in Favorite.query.filter_by(manga_id=manga.id).all():
            favorite.work_id = sw.work_id
        for chapter in Chapter.query.filter_by(manga_id=manga.id).all():
            ref_ch = db.session.get(SourceReference, chapter.uuid)
            payload_ch = ref_ch.payload if ref_ch else {}
            sc = db.session.get(SourceChapter, chapter.uuid) or sync_chapters(sw, [{**payload_ch, 'cap_id': chapter.uuid}])[0]
            for read in Readed.query.filter_by(chapter_id=chapter.id).all():
                read.work_id, read.logical_chapter_id = sw.work_id, sc.logical_chapter_id
                progress = ReadingProgress.query.filter_by(user_id=read.user_id, work_id=sw.work_id).first()
                if progress is None:
                    progress = ReadingProgress(user_id=read.user_id, work_id=sw.work_id,
                                               logical_chapter_id=sc.logical_chapter_id, started_at=read.created_at)
                    db.session.add(progress)
                if progress.last_read_at is None or read.updated_at >= progress.last_read_at:
                    progress.logical_chapter_id = sc.logical_chapter_id
                    progress.last_source, progress.last_source_chapter_id = sw.source, sc.id
                    progress.last_read_at = read.updated_at
                    progress.completed_at = read.updated_at if read.completed else None
                    progress.page_number, progress.page_count = read.page_number, read.page_count
                    progress.progress_percent = read.progress_percent if read.page_count else (1.0 if read.completed else 0.0)
    db.session.flush()

    if 'update_notification' in inspect(db.session.connection()).get_table_names():
        for notification in UpdateNotification.query.all():
            sw = db.session.get(SourceWork, notification.manga_uuid)
            if sw is None:
                ref = db.session.get(SourceReference, notification.manga_uuid)
                sw = resolve_work({'id': notification.manga_uuid, 'title': notification.manga_title},
                                  ref.source if ref else 'mangadex')
            sc = db.session.get(SourceChapter, notification.chapter_uuid)
            if sc is None:
                sc = sync_chapters(sw, [{'cap_id': notification.chapter_uuid, 'cap': notification.chapter_label}])[0]
            notification.work_id = sw.work_id
            notification.logical_chapter_id = sc.logical_chapter_id
    db.session.flush()


def matching_candidates(item, limit=5):
    """Bounded suggestions for reconciliation; fuzzy scores never mutate identity."""
    token = normalize_title(item.get('title')).split(' ')[0]
    if not token:
        return []
    rows = Work.query.filter(Work.normalized_title.startswith(token, autoescape=True)).limit(100).all()
    suggestions = []
    for row in rows:
        if row.metadata_json.get('redirect_to'):
            continue
        score, reason = match_confidence(item, work_data(row))
        if score >= .85:
            suggestions.append({'work_id': row.id, 'confidence': score, 'reason': reason})
    return sorted(suggestions, key=lambda r: (-r['confidence'], r['work_id']))[:limit]
