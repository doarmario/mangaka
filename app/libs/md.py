"""MangaDex adapter. Redis stores plain data, never library/session objects."""
from copy import deepcopy
from hashlib import sha256
import json
import math
import random as rd
from urllib.parse import urlencode

import mangadex as dex
from mangadex.url_models import URLRequest
from mangadex.errors import ApiError
from flask_login import current_user
from sqlalchemy.orm import aliased, joinedload
from sqlalchemy.sql import func

from app import cache, db
from app.models import Manga, Favorite, Readed, Chapter


LANGUAGE_NAMES = {"pt-br": "Português (Brasil)", "pt": "Português (Portugal)", "en": "English"}


class Mangas:
    def __init__(self, lang=None, langs=None, limit=20, prefix="mangadex_"):
        self.languages = (lang,) if lang else ("pt-br", "pt", "en")
        self.langs = tuple(dict.fromkeys(langs or self.languages))
        self.limit = limit
        self.prefix = prefix + "v3_"
        self.mangas = dex.series.Manga()
        self.tags = dex.series.Tag()
        self.covers = dex.series.Cover()
        self.author = dex.people.Author()
        self.chapters = dex.series.Chapter()

    def _key(self, resource, *args):
        params = json.dumps([self.languages, self.langs, self.limit, args], ensure_ascii=False)
        return self.prefix + resource + "_" + sha256(params.encode()).hexdigest()

    def _cached(self, resource, args, loader, timeout=900):
        key = self._key(resource, *args)
        data = cache.get(key)
        if data is None:
            # A shared cooldown also protects uncached queries after a 429.
            cooldown = cache.get(self.prefix + "rate_limit")
            if cooldown:
                raise ApiError({"status": 429, "reason": "MangaDex cooldown"})
            try:
                data = loader()
            except ApiError as exc:
                if str(exc.code) == "429":
                    headers = getattr(exc.resp, "headers", {})
                    try:
                        retry = max(1, int(headers.get("Retry-After", 60)))
                    except (ValueError, TypeError):
                        retry = 60
                    cache.set(self.prefix + "rate_limit", True, timeout=retry)
                raise
            cache.set(key, data, timeout=timeout)
        return deepcopy(data)

    def _text(self, values, fallback=""):
        values = values or {}
        return next((values[lang] for lang in self.langs if values.get(lang)),
                    next((v for v in values.values() if v), fallback))

    def _title(self, manga):
        values = dict(manga.title or {})
        for alternative in manga.alt_titles or []:
            for lang, value in alternative.items():
                values.setdefault(lang, value)
        return self._text(values, "Sem título")

    def _manga_data(self, manga):
        return {"id": manga.manga_id, "title": self._title(manga),
                "sinopse": self._text(manga.description, "Sem descrição"),
                "tags": [self._text(tag.name) for tag in manga.tags],
                "authors": list(manga.author_id), "cover_id": manga.cover_id,
                "ano": manga.year, "status": manga.status}

    def _list(self, offset, **filters):
        offset = max(0, min(int(offset), 10000 - self.limit))
        params = {"availableTranslatedLanguage[]": list(self.languages),
                  "limit": self.limit, "offset": offset, **filters}

        def load():
            # get_manga_list discards total in the pinned library. Keep the
            # response envelope, but use its real parser for manga objects.
            response = URLRequest.request_url(
                self.mangas.api.url + "/manga", "GET",
                timeout=self.mangas.api.timeout, params=params)
            items = dex.series.Manga.create_manga_list(response)
            # Listing records already contain the metadata needed by details.
            # Reuse them when a card is opened or its cover is requested.
            for manga in items:
                cache.set(self._key("manga", manga.manga_id),
                          self._manga_data(manga), timeout=3600)
            return {"itens": [{"id": m.manga_id, "title": self._title(m)} for m in items],
                    "total": response["total"]}

        return self._cached("list", (params,), load)

    def getTotalPages(self):
        return self.listAll(0)["total"]

    def listAll(self, offset):
        return self._list(offset, **{"order[title]": "asc"})

    def listRecents(self, offset):
        return self._list(offset, **{"order[latestUploadedChapter]": "desc"})

    def listMangaByTag(self, tag_id, offset):
        return self._list(offset, **{"includedTags[]": [tag_id]})

    def listaGeral(self, offset=0):
        return self.listAll(offset)

    def recentes(self, offset=0):
        return {"tag": "Recentes", **self.listRecents(offset)}

    def searchMangaByTitle(self, title, offset=0):
        return self._list(offset, title=title.strip())

    def listTags(self):
        return self._cached("tags", (), lambda: [
            {"id": tag.tag_id, "name": self._text(tag.name, "Sem categoria")}
            for tag in self.tags.tag_list()], timeout=86400)

    def choiceTags(self, offset=0):
        tags = self.listTags()
        if not tags:
            return {"tag": "Categorias", "itens": [], "total": 0}
        tag = rd.choice(tags)
        return {"tag": tag["name"], **self.listMangaByTag(tag["id"], offset)}

    def getManga(self, uuid):
        def load():
            manga = self.mangas.get_manga_by_id(manga_id=uuid)
            return self._manga_data(manga)
        return self._cached("manga", (uuid,), load, timeout=3600)

    def id2Cover(self, uuid):
        def load():
            cover_id = self.getManga(uuid)["cover_id"]
            if not cover_id:
                return "/static/img/page.png"
            return self.covers.get_cover(cover_id=cover_id).fetch_cover_image()
        return self._cached("cover", (uuid,), load, timeout=3600)

    def lista_ultimos_favoritos(self,  offset):
        # Consultando os 20 últimos favoritos do usuário, ordenados por 'created_at' de forma decrescente
        favoritos = Favorite.query.options(joinedload(Favorite.manga)).filter_by(user_id=current_user.id).order_by(Favorite.id.desc()).offset(offset).limit(20).all()
        
        # Montando a lista de favoritos no formato desejado
        data = [{
                "title": f"{fav.manga.title}",  # Ajuste conforme o campo correto para o título do manga
                "id": fav.manga.uuid  # Usando o UUID do manga, altere conforme necessário
            } for fav in favoritos]
        return data

    def continuar_lendo(self, offset):
        # Subquery para obter o max updated_at por manga
        subquery = (
            db.session.query(
                Chapter.manga_id.label("manga_id"),
                func.max(Readed.updated_at).label("latest_read")
            )
            .join(Readed, Readed.chapter_id == Chapter.id)
            .filter(Readed.user_id == current_user.id)
            .group_by(Chapter.manga_id)
            .subquery()
        )

        # Aliased para fazer o join correto
        r2 = aliased(Readed)
        c2 = aliased(Chapter)

        chapters_read = (
            db.session.query(r2)
            .options(joinedload(r2.chapter).joinedload(Chapter.manga))
            .filter(r2.user_id == current_user.id)
            .join(c2, r2.chapter_id == c2.id)
            .join(subquery, (c2.manga_id == subquery.c.manga_id) & (r2.updated_at == subquery.c.latest_read))
            .order_by(r2.updated_at.desc())
            .offset(offset)
            .limit(20)
            .all()
        )

        data = [{
            "title": read.chapter.manga.title,
            "id": read.chapter.manga.uuid,
            "chapter": read.chapter.uuid  # Aqui pega o UUID do capítulo lido
        } for read in chapters_read]
        
        return data


    
    @staticmethod
    def _chapter_order(chapter):
        try:
            number = float(chapter["cap"])
            if math.isfinite(number):
                return (1, number)
        except (ValueError, TypeError):
            pass
        return (0, 0)

    def getMangaChapterList(self, manga_id, is_read=True, language=None):
        def load(language):
            volumes = self.mangas.get_manga_volumes_and_chapters(
                manga_id=manga_id, translatedLanguage=[language])
            data = []
            for volume in volumes.values() if isinstance(volumes, dict) else volumes:
                chapters = volume["chapters"]
                # The aggregate endpoint can encode empty collections as [].
                for chapter in chapters.values() if isinstance(chapters, dict) else chapters:
                    number = chapter.get("chapter")
                    data.append({"cap": str(number) if number not in (None, "none") else "Sem número",
                                 "cap_id": chapter["id"], "language": language,
                                 "language_name": LANGUAGE_NAMES.get(language, language),
                                 "others": chapter.get("others", []), "is_readed": False})
            return sorted(data, key=self._chapter_order, reverse=True)

        # Aggregate responses do not include a language per chapter. Fetch
        # and cache each language separately so equal chapter numbers remain
        # distinct and the reader never jumps between translations.
        data = []
        for selected in ((language,) if language else self.languages):
            data.extend(self._cached("chapters", (manga_id, selected),
                                     lambda: load(selected)))
        data.sort(key=self._chapter_order, reverse=True)
        if is_read and current_user.is_authenticated:
            ids = [c["cap_id"] for c in data]
            read_ids = {uuid for (uuid,) in db.session.query(Chapter.uuid).join(Readed).filter(
                Readed.user_id == current_user.id, Chapter.uuid.in_(ids)).all()}
            for chapter in data:
                chapter["is_readed"] = chapter["cap_id"] in read_ids
        return data

    def getChapter(self, cap_id):
        def load():
            cap = self.chapters.get_chapter_by_id(chapter_id=cap_id)
            return {"id": cap.chapter_id, "cap": cap.chapter,
                    "manga_id": cap.manga_id, "language": cap.translated_language,
                    "language_name": LANGUAGE_NAMES.get(cap.translated_language, cap.translated_language)}
        metadata = self._cached("chapter", (cap_id,), load, timeout=3600)
        manga = self.getManga(metadata["manga_id"])
        caps = self.getMangaChapterList(metadata["manga_id"], is_read=False,
                                        language=metadata["language"])
        index = next((n for n, c in enumerate(caps)
                      if cap_id == c["cap_id"] or cap_id in c["others"]), None)

        def images():
            chapter = dex.series.Chapter()
            chapter.chapter_id = cap_id
            return chapter.fetch_chapter_images()
        # At-home URLs expire; keep their cache separate from chapter metadata.
        urls = self._cached("pages", (cap_id,), images, timeout=600)
        return {**metadata, "manga": manga["title"],
                "pages": ["/img/page/proxy?" + urlencode({"url": url}) for url in urls],
                "index": index, "caps": len(caps) - 1,
                "prev": caps[index + 1]["cap_id"] if index is not None and index + 1 < len(caps) else None,
                "next": caps[index - 1]["cap_id"] if index is not None and index > 0 else None}

    def showManga(self, manga_id):
        manga = self.getManga(manga_id)
        caps = self.getMangaChapterList(manga_id)
        authors = [self._cached("author", (author_id,),
                    lambda: self.author.get_author_by_id(author_id).name, timeout=86400)
                   for author_id in manga["authors"]]
        available = [{"code": language, "name": LANGUAGE_NAMES.get(language, language)}
                     for language in self.languages if any(c["language"] == language for c in caps)]
        preferred = [c for c in caps if available and c["language"] == available[0]["code"]]
        data = {"languages": available, "first_chapter": preferred[-1]["cap_id"] if preferred else None,
                **manga, "autor": ", ".join(authors), "chapters": caps,
                "caps": len(caps), "is_favorite": False}
        if current_user.is_authenticated:
            data["is_favorite"] = db.session.query(Favorite).join(Manga).filter(
                Favorite.user_id == current_user.id, Manga.uuid == manga_id).first() is not None
        return data
