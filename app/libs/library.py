"""Route-facing library; IDs determine the provider for details and reading."""
from flask import abort, current_app, request
from flask_login import current_user
from app import db
from app.libs.md import Mangas
from app.libs.manga_novel import MangaNovel, SOURCES
from app.models import SourceReference, Manga, Chapter, Favorite, Readed


class Library(Mangas):
    @staticmethod
    def sources():
        return {'mangadex': 'MangaDex', **(SOURCES if current_app.config.get('MANGA_NOVEL_API_URL') else {})}

    @classmethod
    def selected_source(cls):
        source = request.args.get('source', 'mangadex')
        if source not in cls.sources():
            abort(400, 'Fonte desconhecida ou não configurada.')
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

    def showManga(self, manga_id):
        ref = self.reference(manga_id, 'manga')
        if not ref:
            return {**super().showManga(manga_id), 'source_name': 'MangaDex', 'source_id': 'mangadex'}
        adapter = MangaNovel(ref.source)
        data = adapter.info(ref)
        chapters = adapter.chapters(ref)
        if current_user.is_authenticated:
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
        favorite = current_user.is_authenticated and db.session.query(Favorite).join(Manga).filter(
            Favorite.user_id == current_user.id, Manga.uuid == manga_id).first() is not None
        return {**data, 'source_id': ref.source, 'chapters': chapters, 'caps': len(chapters), 'languages': languages,
                'first_chapter': preferred[-1]['cap_id'] if preferred else None, 'is_favorite': bool(favorite)}

    def getChapter(self, cap_id):
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
        return {**ref.payload, 'id': ref.id, 'manga_id': parent.id, 'manga': info['title'],
                'source_name': SOURCES[ref.source], 'pages': adapter.pages(ref, parent),
                'index': index, 'caps': len(chapters) - 1,
                'prev': chapters[index + 1]['cap_id'] if index is not None and index + 1 < len(chapters) else None,
                'next': chapters[index - 1]['cap_id'] if index is not None and index > 0 else None}
