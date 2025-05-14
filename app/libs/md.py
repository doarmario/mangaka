import mangadex as dex
import datetime as dt
import random as rd
import markdown as md

from app import cache, db
from app.models import Manga, Favorite, Readed, Chapter

from flask_login import current_user
from sqlalchemy.orm import aliased
from sqlalchemy.sql import func

import time


class Mangas:
    def __init__(self,lang='pt-br',langs=['es','en','pt-br','pt'],limit=20,prefix="mangadex_"):

        self.lang = lang
        self.langs = langs
        self.limit = limit
        
        self.prefix = prefix

        self.auth = dex.auth.Auth()
        self.tags = dex.series.Tag()
        self.covers = dex.series.Cover()
        self.mangas = dex.series.Manga(auth=self.auth)
        self.author = dex.people.Author(auth=self.auth)
        self.chapters = dex.series.Chapter(auth=self.auth)


    #cached functions

    def listAll(self,offset):

        key = f"{self.prefix}listall_{offset}"

        data = cache.get(key)

        if data is None:
            data = self.mangas.get_manga_list(
                translatedLanguage=self.lang,
                limit=self.limit,
                offset=offset
            )
        
            cache.set(key,data,timeout=3600)

        return data

    def listRecents(self):

        key = f"{self.prefix}recents"

        data = cache.get(key)


        if data is None:
            data = self.mangas.get_manga_list(
                translatedLanguage=self.lang,
                limit=self.limit,
                updatedAtSince=(dt.datetime.now() - dt.timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%S')
            )
            cache.set(key,data,timeout=900)

        return data

    def getManga(self,uuid):
        key = f"{self.prefix}manga_{uuid}"

        data = cache.get(key)

        if data is None:
            data = self.mangas.get_manga_by_id(manga_id=uuid)
            cache.set(key,data,timeout=3600)

        return data

    def id2Cover(self,uuid):

        key = f"{self.prefix}cover_{uuid}"

        data = cache.get(key)

        if data is None:
        
            content = self.getManga(uuid)
            data = self.covers.get_cover(
                cover_id=content.cover_id
            ).fetch_cover_image()

            cache.set(key,data,timeout=3600)

        return data

    def listMangaByTag(self,tag_id):
        
        key = f"{self.prefix}tag_{tag_id}"

        data = cache.get(key)

        if data is None:
            data = self.mangas.get_manga_list(
                translatedLanguage=self.lang,
                limit=self.limit,
                includedTags=[tag_id]
            )
            cache.set(key,data,timeout=360)

        return data

    def recentes(self):
        
        a = self.listRecents()
        return  {"tag":"Recentes","itens":[{
            "title": i.title.get('en') or next(
                (alt[lang] for alt in i.alt_titles for lang in self.langs if lang in alt),
                "No title"
            ),
            "id":i.manga_id
            } for i in a]}

    def listTags(self):

        key = f"{self.prefix}tags"

        data = cache.get(key)

        if data is None:
            data =self.tags.tag_list()

            cache.set(key,data,timeout=3600)

        return data

    def choiceTags(self):

        t = rd.choice(self.listTags())
        
        key = f"{self.prefix}rtags_{t.name['en']}"

        data = cache.get(key)

        if data is None:
            d = self.listMangaByTag(t.tag_id)

            data = {
                "tag":t.name['en'],
                "itens":[{
                    "title": i.title.get('en') or next(
                        (alt[lang] for alt in i.alt_titles for lang in self.langs if lang in alt), "No title"
                        ),
                    "id":i.manga_id
                } for i in d]
            }

            cache.set(key,data,timeout=3600)

        return data

    def listaGeral(self,offset):
        l = self.listAll(offset)
        data = [{
                "title": i.title.get('en') or next(
                    (alt[lang] for alt in i.alt_titles for lang in self.langs if lang in alt),
                     None),
                "id":i.manga_id

            } for i in l]
        return data

    def lista_ultimos_favoritos(self,  offset):
        # Consultando os 20 últimos favoritos do usuário, ordenados por 'created_at' de forma decrescente
        favoritos = Favorite.query.filter_by(user_id=current_user.id).order_by(Favorite.id.desc()).offset(offset).limit(20).all()
        
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


    
    def getMangaChapterList(self, manga_id, is_read=True):
        key = f"{self.prefix}manga_{manga_id}_chapters"
        data = cache.get(key)

        if data is None:
            cp = self.mangas.get_manga_volumes_and_chapters(
                manga_id=manga_id,
                translatedLanguage=self.lang
            )
            data = [
                {
                    "cap": cp[i]['chapters'][j]["chapter"] if cp[i]['chapters'][j]['chapter'] != 'none' else str(n+1),
                    "cap_id": cp[i]['chapters'][j]['id'],
                    "is_readed": False
                }
                for i in cp for n,j in enumerate(cp[i]['chapters'].keys())
            ]
            data.sort(key=lambda i: float(i["cap"]), reverse=True)
            cache.set(key, data, timeout=900)

        if current_user.is_authenticated and is_read:
            # Etapa 1: coletar todos os UUIDs dos capítulos
            all_cap_ids = [chapter["cap_id"] for chapter in data]

            # Etapa 2: obter todos os capítulos lidos de uma vez
            read_uuids = db.session.query(Chapter.uuid).join(Readed).filter(
                Readed.user_id == current_user.id,
                Chapter.uuid.in_(all_cap_ids)
            ).all()

            # Etapa 3: converter o resultado em um conjunto para busca rápida
            read_uuids_set = set(uuid for (uuid,) in read_uuids)

            # Etapa 4: atualizar os capítulos com base no conjunto
            for chapter in data:
                chapter["is_readed"] = chapter["cap_id"] in read_uuids_set


        return data

    def getChapter(self,cap_id):

        key = f"{self.prefix}chapter_{cap_id}"

        data = cache.get(key)

        if data is None:
            cap = self.chapters.get_chapter_by_id(chapter_id=cap_id)
            manga = self.getManga(cap.manga_id)
            caps = self.getMangaChapterList(cap.manga_id,is_read=False)

            index = next((index for index, i in enumerate(caps) if i["cap_id"] == cap_id), None)
            if  len(caps)-1 <= index:
                prev = None
            else:
                prev = caps[index+1]["cap_id"]

            if index < 0:
                nxt = None
            else:
                nxt = caps[index-1]["cap_id"]
                    
            data = {
                "id":cap.chapter_id,
                "cap":cap.chapter,
                "pages": [f"/img/page/proxy?url={i}" for i in cap.fetch_chapter_images()],
                "manga": manga.title.get('en') or next(
                    (alt[lang] for alt in manga.alt_title for lang in self.langs if lang in alt),
                    "No title"
                ),
                "manga_id":manga.manga_id,
                "index":index,
                "caps":len(caps)-1,
                "prev": prev,
                "next": nxt
            }

            cache.set(key,data,timeout=900)
        print(data)
        return data

    def showManga(self, manga_id):
        manga = self.getManga(manga_id)
        caps = self.getMangaChapterList(manga.manga_id)
        data = {
            "id":manga.manga_id,
            "title": manga.title.get('en') or next(
                    (alt[lang] for alt in manga.alt_title for lang in self.langs if lang in alt),
                    'No title'
                ),
            "sinopse": manga.description.get('en') or next(
                (alt[lang] for alt in manga.description for lang in self.langs if lang in alt),
                "No description!"
            ),
            "tags": [i.name.get('en') for i in manga.tags],
            "caps":len(caps),
            "autor": ", ".join(
                [self.author.get_author_by_id(i).name for i in manga.author_id]
            ),
            "ano":manga.year,
            "chapters":caps,
            "status":manga.status,
            "is_favorite": False
        }
        # Atualizando o status de leitura dos capítulos após salvar no cache
        if current_user.is_authenticated:
            manga_id = data["id"]
            # Verificando se o capítulo foi lido
            is_fav = db.session.query(Favorite).join(Manga).filter(
                Favorite.user_id == current_user.id,
                Manga.uuid == manga_id  # Verificando pelo UUID do capítulo
            ).first() is not None  # Se existir, o capítulo foi lido
            data["is_favorite"] = is_fav
        print(data)
        return data

    def searchMangaByTitle(self, title):

        key = f"{self.prefix}search_{title}"

        data = cache.get(key)

        if data is None:

            mangas = self.mangas.get_manga_list(
                translatedLanguage=self.lang,
                limit=self.limit,
                title=title
            )
            data = [{
                "title": m.title.get('en') or next(
                    (alt[lang] for alt in m.alt_titles for lang in self.langs if lang in alt),
                    None),
                "id": m.manga_id  # Ou m.manga_id, dependendo de como o objeto Manga é estruturado
            } for m in mangas]

            cache.set(key,data,timeout=3600)
        
        return data

        

