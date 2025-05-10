import mangadex as dex
import datetime as dt
import random as rd
import markdown as md

from app import cache


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
                None
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
                        (alt[lang] for alt in i.alt_titles for lang in self.langs if lang in alt), None
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

    def getMangaChapterList(self,manga_id):

        key = f"{self.prefix}manga_{manga_id}_chapters"

        data = cache.get(key)

        if data is None:
            cp = self.mangas.get_manga_volumes_and_chapters(
                manga_id=manga_id,
                translatedLanguage=self.lang
            )
            data = [
                {
                    "cap":cp[i]['chapters'][j]["chapter"],
                    "cap_id":cp[i]['chapters'][j]['id']
                } for i in cp for j in cp[i]["chapters"].keys()
            ]
            data.sort(key=lambda i:float(i["cap"]),reverse=True)
            cache.set(key,data,timeout=900)

        return data

    def getChapter(self,cap_id):

        key = f"{self.prefix}chapter_{cap_id}"

        data = cache.get(key)

        if data is None:
            cap = self.chapters.get_chapter_by_id(chapter_id=cap_id)
            manga = self.getManga(cap.manga_id)

            data = {
                "cap":cap.chapter,
                "pages": [f"/img/page/proxy?url={i}" for i in cap.fetch_chapter_images()],
                "manga": manga.title.get('en') or next(
                    (alt[lang] for alt in manga.alt_title for lang in self.langs if lang in alt),
                    None
                )
            }

            cache.set(key,data,timeout=900)
        return data

    def showManga(self, manga_id):
        manga = self.getManga(manga_id)
        caps = self.getMangaChapterList(manga.manga_id)
        data = {
            "id":manga.manga_id,
            "title": manga.title.get('en') or next(
                    (alt[lang] for alt in manga.alt_title for lang in self.langs if lang in alt),
                    None
                ),
            "sinopse": manga.description['en'],
            "tags": [i.name['en'] for i in manga.tags],
            "caps":len(caps),
            "autor": ", ".join(
                [self.author.get_author_by_id(i).name for i in manga.author_id]
            ),
            "ano":manga.year,
            "chapters":caps,
            "status":manga.status
        }
        return data


        

