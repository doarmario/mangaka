"""Route-facing library; IDs determine the provider for details and reading."""
from flask import abort, request
from flask_login import current_user
from sqlalchemy.orm import joinedload
from app import db
from app.libs.md import Mangas
from app.libs.manga_novel import MangaNovel, SOURCES, VISIBLE_SOURCES, source_api_url
from app.models import SourceReference, Manga, Chapter, Favorite, Readed, SourceWork


class Library(Mangas):
    @staticmethod
    def sources():
        return {'mangadex': 'MangaDex', **{key: name for key, name in VISIBLE_SOURCES.items()
                                          if source_api_url(key)}}

    @classmethod
    def selected_source(cls):
        default = 'all' if len(cls.sources()) > 1 else 'mangadex'
        if request.endpoint == 'user.tags' or any(request.args.get(k) for k in ('tag', 'language', 'status')):
            default = 'mangadex'
        source = request.args.get('source', default)
        if source == 'all':
            return 'mangadex' if request.endpoint == 'user.tags' else source
        # Keep old provider URLs readable for existing bookmarks, while hiding
        # disabled providers from the catalog selector.
        configured = source_api_url(source)
        if source not in cls.sources() and not (configured and source in SOURCES):
            abort(400, 'Unknown or unconfigured source.')
        return source

    @staticmethod
    def reference(identifier, kind):
        ref = db.session.get(SourceReference, identifier)
        if ref and ref.kind != kind:
            abort(404)
        return ref

    def id2Cover(self, uuid, size=None):
        ref = self.reference(uuid, 'manga')
        if ref:
            adapter = MangaNovel(ref.source)
            cover = ref.payload.get('coverUrl') or adapter.info(ref)['cover_url']
            return adapter.image_proxy_url(cover)
        url = super().id2Cover(uuid)
        return url + f'.{size}.jpg' if size and not url.startswith('/static/') else url

    def _source_manga(self, manga_id):
        ref = self.reference(manga_id, 'manga')
        if not ref:
            return {**super().showManga(manga_id), 'source_name': 'MangaDex', 'source_id': 'mangadex'}
        adapter = MangaNovel(ref.source)
        data = adapter.info(ref)
        chapters = adapter.chapters(ref)
        if current_user and current_user.is_authenticated:
            read = {uuid for (uuid,) in db.session.query(Chapter.uuid).join(Readed).filter(
                Readed.user_id == current_user.id, Chapter.uuid.in_([c['cap_id'] for c in chapters])).all()}
            for chapter in chapters:
                chapter['is_readed'] = chapter['cap_id'] in read
        languages = []
        for lang in ('pt-br', 'pt', 'en'):
            match = next((c for c in chapters if c['language'] == lang), None)
            if match:
                languages.append({'code': lang, 'name': match['language_name']})
        preferred = [c for c in chapters if languages and c['language'] == languages[0]['code']]
        favorite = current_user and current_user.is_authenticated and db.session.query(Favorite).join(Manga).filter(
            Favorite.user_id == current_user.id, Manga.uuid == manga_id).first() is not None
        return {**data, 'source_id': ref.source, 'chapters': chapters, 'caps': len(chapters), 'languages': languages,
                'first_chapter': preferred[-1]['cap_id'] if preferred else None, 'is_favorite': bool(favorite)}

    def _source_chapter(self, cap_id):
        ref = self.reference(cap_id, 'chapter')
        if not ref:
            return {**super().getChapter(cap_id), 'source_name': 'MangaDex', 'source_id': 'mangadex'}
        parent = self.reference(ref.parent_id, 'manga')
        if not parent:
            abort(404)
        adapter = MangaNovel(ref.source)
        info = adapter.info(parent)
        chapters = [c for c in adapter.chapters(parent) if c['language'] == ref.payload['language']]
        index = next((i for i, c in enumerate(chapters) if c['cap_id'] == cap_id), None)
        return {**ref.payload, 'id': ref.id, 'manga_id': parent.id, 'manga': info['title'], 'work_metadata': info,
                'source_name': SOURCES[ref.source], 'source_id': ref.source, 'pages': adapter.pages(ref, parent),
                'index': index, 'caps': len(chapters) - 1,
                'prev': chapters[index + 1]['cap_id'] if index is not None and index + 1 < len(chapters) else None,
                'next': chapters[index - 1]['cap_id'] if index is not None and index > 0 else None}

    def favorite_updates(self, limit=20):
        """Return favorite titles whose latest chapters are still unread."""
        favorites = Favorite.query.options(joinedload(Favorite.manga)).filter_by(
            user_id=current_user.id).order_by(Favorite.id.desc()).limit(limit).all()
        updates, seen = [], set()
        for favorite in favorites:
            identity = favorite.work_id or favorite.manga.uuid
            if identity in seen:
                continue
            seen.add(identity)
            try:
                data = self.work_details(favorite.work) if favorite.work else self.showManga(favorite.manga.uuid)
            except Exception:
                # One unavailable provider must not hide updates from others.
                continue
            unread = [chapter for chapter in data.get('chapters', []) if not chapter.get('is_readed')]
            if not unread:
                continue
            latest = unread[0]
            updates.append({
                'id': data.get('id', favorite.manga.uuid),
                'work_id': favorite.work_id,
                'title': data.get('title', favorite.manga.title),
                'chapter': latest.get('cap_id'),
                'source_name': data.get('source_name', 'MangaDex'),
                'latest_chapter': latest.get('cap', 'Unnumbered'),
                'unread_count': len(unread),
            })
        return updates


    def showManga(self, manga_id):
        from app.libs.canonical import resolve_work, sync_chapters
        from app.models import ReadingProgress
        data = self._source_manga(manga_id)
        sw = resolve_work(data, data['source_id'])
        mapped = sync_chapters(sw, data.get('chapters', []), complete=True)
        data['work_id'] = sw.work_id
        data['reading_progress'] = None
        if current_user and current_user.is_authenticated:
            read_ids = {r.logical_chapter_id for r in Readed.query.filter_by(
                user_id=current_user.id, work_id=sw.work_id, completed=True).all()}
            mapping = {c.id: c for c in mapped}
            for chapter in data.get('chapters', []):
                chapter['is_readed'] = chapter.get('is_readed', False) or mapping[chapter['cap_id']].logical_chapter_id in read_ids
            data['is_favorite'] = data.get('is_favorite', False) or Favorite.query.filter_by(
                user_id=current_user.id, work_id=sw.work_id).first() is not None
            data['reading_progress'] = ReadingProgress.query.filter_by(user_id=current_user.id, work_id=sw.work_id).first()
        db.session.commit()
        return data

    def getChapter(self, cap_id):
        from app.libs.canonical import resolve_work, sync_chapters
        data = self._source_chapter(cap_id)
        sw = resolve_work(data.get('work_metadata') or {'id': data['manga_id'], 'title': data['manga']}, data['source_id'])
        sc = sync_chapters(sw, [{**data, 'cap_id': data['id']}])[0]
        data['work_id'], data['logical_chapter_id'] = sw.work_id, sc.logical_chapter_id
        db.session.commit()
        return data

    def discover_work_sources(self, work):
        from app.libs.catalog import UnifiedCatalog, matches
        from app.libs.canonical import resolve_work, work_data
        from app import cache
        from app.libs.reading import PROVIDER_ERRORS
        key = 'canonical-discovery-v1:' + work.id
        if cache.get(key):
            return
        known = {s.source for s in work.sources}
        failed = False
        for source in self.sources():
            if source in known:
                continue
            try:
                result = UnifiedCatalog(self).provider(source, work.canonical_title, 1)
                candidates = [item for item in result['itens'] if matches(work_data(work), item)]
                if len(candidates) == 1:
                    resolve_work(candidates[0], source)
                    db.session.commit()
            except PROVIDER_ERRORS:
                failed = True
        db.session.expire(work, ['sources'])
        cache.set(key, True, timeout=60 if failed else 3600)

    def work_details(self, work):
        from app.libs.reading import source_order, PROVIDER_ERRORS
        from app.models import ReadingProgress
        progress = (ReadingProgress.query.filter_by(user_id=current_user.id, work_id=work.id).first()
                    if current_user and current_user.is_authenticated else None)
        for sw in source_order(work, self, progress):
            try:
                data = self.showManga(sw.id)
                break
            except PROVIDER_ERRORS:
                sw.available = False
                db.session.commit()
        else:
            first = next(iter(work.sources), None)
            data = {'id': first.id if first else work.id, 'title': work.canonical_title,
                    'sinopse': work.description or '', 'chapters': [], 'caps': 0,
                    'languages': [], 'source_id': first.source if first else '',
                    'source_name': 'Sources unavailable', 'tags': [], 'tag_links': [],
                    'is_favorite': bool(current_user and current_user.is_authenticated and
                                        Favorite.query.filter_by(user_id=current_user.id, work_id=work.id).first())}
        return {**data, 'work_id': work.id, 'title': work.canonical_title,
                'reading_progress': progress, 'work_sources': work.sources}

    def continuar_lendo(self, offset):
        from app.models import ReadingProgress
        rows = ReadingProgress.query.filter_by(user_id=current_user.id).filter(ReadingProgress.logical_chapter_id.isnot(None)).order_by(
            ReadingProgress.last_read_at.desc()).offset(offset).limit(20).all()
        result = [{'id': next((s.id for s in row.work.sources), row.work_id),
                   'work_id': row.work_id, 'title': row.work.canonical_title,
                   'chapter': row.last_source_chapter_id, 'resume': True} for row in rows]
        # Existing imports not yet backfilled still have their original links.
        known = {item['id'] for item in result}
        result.extend(item for item in super().continuar_lendo(offset) if item['id'] not in known
                      and not db.session.query(ReadingProgress.id).join(
                          SourceWork,
                          SourceWork.work_id == ReadingProgress.work_id
                      ).filter(ReadingProgress.user_id == current_user.id,
                               SourceWork.id == item['id']).first())
        return result[:20]

    def lista_ultimos_favoritos(self, offset):
        rows = Favorite.query.filter_by(user_id=current_user.id).order_by(Favorite.id.desc()).all()
        result, seen = [], set()
        for row in rows:
            key = row.work_id or row.manga.uuid
            if key in seen:
                continue
            seen.add(key)
            result.append({'id': row.manga.uuid, 'work_id': row.work_id,
                           'title': row.work.canonical_title if row.work else row.manga.title})
        return result[offset:offset + 20]
