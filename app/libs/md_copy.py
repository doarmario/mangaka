import mangadex as md
import datetime as dt
import random as rd

class Mangas:

    def __init__(self, lang='pt-br'):
        self.lang = lang
        self.auth = md.auth.Auth()
        self.limit = 20

    # Função para listar todos os mangas com limite
    def listAll(self, offset,*args):
        manga = md.series.Manga(auth=self.auth)
        # Retorna uma lista de mangas como objetos
        manga_list = manga.get_manga_list(
            translatedLanguage=self.lang,
            limit=self.limit,
            offset=offset
        )
        return manga_list  # Retorna como objetos Manga

    # Função para listar mangas recentes
    def listRecent(self, *args):
        manga = md.series.Manga(auth=self.auth)
        date = (dt.datetime.now() - dt.timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%S')
        # Retorna uma lista de mangas como objetos
        manga_list = manga.get_manga_list(
            translatedLanguage=self.lang,
            limit=self.limit,
            updatedAtSince=date
        )
        return manga_list  # Retorna como objetos Manga

    # Função para listar tags
    def listTags(self):
        tag = md.series.Tag()
        # Retorna as tags como objetos
        tag_list = tag.tag_list()
        return tag_list  # Retorna como lista de objetos Tag

    def cover2id(self,uid):
        manga = md.series.Manga(auth=self.auth)
        content = manga.get_manga_by_id(manga_id=uid)
        cover = md.series.Cover()
        return cover.get_cover(cover_id=content.cover_id).fetch_cover_image()

    # Função para pesquisar mangas por título
    def searchMangaByTitle(self, title):
        manga = md.series.Manga(auth=self.auth)
        # Retorna uma lista de mangas como objetos
        mangas = manga.get_manga_list(
            translatedLanguage=self.lang,
            limit=self.limit,
            title=title
        )
        return mangas  # Retorna como objetos Manga

    # Função para abrir um manga específico pelo manga_id
    def getMangaDetails(self, manga_id):
        manga = md.series.Manga(auth=self.auth)
        # Retorna o manga como objeto
        manga_details = manga.get_manga(manga_id)
        return manga_details  # Retorna como objeto Manga

    # Função para listar os capítulos de um manga específico
    def listChapters(self, manga_id):
        manga = md.series.Manga(auth=self.auth)
        # Retorna os capítulos como objetos
        chapters = manga.get_chapters(manga_id)
        return chapters  # Retorna como lista de objetos Chapter

    # Função para abrir as URLs das páginas de um capítulo específico
    def listChapterPages(self, chapter_id):
        chapter = md.series.Chapter(auth=self.auth)
        chapter_details = chapter.get_chapter(chapter_id)
        # Retorna as páginas do capítulo como lista
        return chapter_details['data']['attributes']['pages']  # Retorna as páginas como lista de URLs

    ###################################

    # Função para pegar os mangas recentes com suas capas
    def recentes(self):
        a = self.listRecent()
        data = []
        for i in a:
            #print(dir(i))
            data.append({
                "title": i.title.get('en') or next((alt[lang] for alt in i.alt_titles for lang in ['en', 'es', 'pt'] if lang in alt), None),
                "id": i.manga_id
            })
        return {'tag':"Recentes","itens":data}

    # Função para listar mangas por tag
    def listMangasByTag(self, tag_id):
        manga = md.series.Manga(auth=self.auth)
        # Filtra mangas pela tag especificada
        manga_list = manga.get_manga_list(
            translatedLanguage=self.lang,
            limit=self.limit,
            includedTags=[tag_id]
        )
        return manga_list  # Retorna uma lista de mangas como objetos

    def randomTag(self):
        t = self.listTags()
        return rd.choice(t)

    def choiceTags(self):
        data = []
        t = self.randomTag()
        d = self.listMangasByTag(t.tag_id)
        for i in d:
            #print(dir(i))
            data.append({
                "title": i.title.get('en') or next((alt[lang] for alt in i.alt_titles for lang in ['en', 'es', 'pt-br'] if lang in alt), None),
                "id": i.manga_id
            })
        return {'tag':t.name['en'],'itens':data}

    def listaGeral(self,offset):
        l = self.listAll(offset)
        data = []
        for i in l:
            #print(dir(i))
            data.append({
                "title": i.title.get('en') or next((alt[lang] for alt in i.alt_titles for lang in ['en', 'es', 'pt-br'] if lang in alt), None),
                "id":i.manga_id
            })
        return data

    def showManga(self,manga_id):

        m = md.series.Manga(auth=self.auth)
        d = m.get_manga_by_id(manga_id=manga_id)

        a = md.people.Author(auth=self.auth)

        t = md.series.Tag()

        c = md.series.Chapter()

        cp = c.get_manga_volumes_and_chapters(manga_id=d.manga_id,translatedLanguage=self.lang)
        
        caps = []
        for i in cp:
            for j in cp[i]['chapters'].keys():
                cap = cp[i]['chapters'][j]
                caps.append({"cap":cap['chapter'],"cap_id":cap['id']})

        caps.sort(key=self.chaptersSort)

        data ={
            "id":d.manga_id,
            "title": d.title.get('en') or next((alt[lang] for alt in d.alt_titles for lang in ['en', 'es', 'pt-br'] if lang in alt), None),
            "sinopse": d.description['en'] ,
            "tags":  [i.name['en'] for i in d.tags],
            "caps":len(caps),
            "autor": ",".join([a.get_author_by_id(i).name for i in d.author_id]),
            "ano":d.year,
            "chapters": caps,
            "status": d.status,
        }
        return data


    def chaptersSort(self,item):
        cap = float(item["cap"])
        return cap

    def getChapter(self,cap_id):
        c = md.series.Chapter(auth=self.auth)
        cap = c.get_chapter_by_id(chapter_id=cap_id)
        manga = md.series.Manga(auth=self.auth).get_manga_by_id(cap.manga_id)
        data={
            "cap": cap.chapter,
            "pages": [f"/img/page/proxy?url={i}" for i in cap.fetch_chapter_images()],
            "manga": manga.title.get('en') or next((alt[lang] for alt in manga.alt_titles for lang in ['en', 'es', 'pt-br'] if lang in alt), None),
        }
        return data


if __name__ == "__main__":
    m = Mangas()

    # Exemplo de listagem dos mangas recentes com suas capas
    #a = m.listaGeral(0)]
    manga = m.showManga('eb50c3d2-f08d-4b71-b507-e0272bbb3577')
    cid = manga['chapters'][0]["cap_id"]
    print(m.getChapter(cid))

