from flask import Blueprint, render_template, redirect, url_for,flash,send_file, Response, request, stream_with_context, jsonify, g
from flask_login import login_user,current_user,logout_user, login_required

from app.models import User, Manga, Favorite, Readed, Chapter

from app.libs.md import Mangas

from app.forms import SearchForm

from app import db, login_manager
from app import cache


from datetime import datetime
from io import BytesIO


import requests
import hashlib
import time
import uuid

site = Blueprint('user', __name__)

header = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36 Mangaka/1.0',
    'Referer': 'https://mangadex.org/'
}

manga = Mangas()


@site.before_request
def before_request():
    g.form = SearchForm()


# Função para gerar chave de cache única por usuário
def get_cache_key():
    """Gera uma chave de cache única por usuário"""
    if current_user.is_authenticated:
        return f"mangaka_user_loged_home"  # Chave única para cada usuário autenticado
    
    return 'home_page'  # Caso não esteja logado, usa uma chave global


header = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64) Chrome/91.0.4472.124',  # Cabeçalho mais simplificado
    'Referer': 'https://mangadex.org/',
    'Accept-Encoding': 'gzip, deflate, br',  # Permite compressão dos dados na resposta
    'Connection': 'keep-alive',  # Para manter a conexão ativa entre as requisições
}


session = requests.Session()
session.headers.update(header)

def Etag(content):
    return hashlib.sha1(content.encode()).hexdigest()


def proxy(url):
    try:
        r = session.get(url, headers=header)

        if r.status_code == 200:
            content = r.content
            etag_value = Etag(url)  # Geração de um ETag único

            response = send_file(BytesIO(content), mimetype='image/jpeg')
            response.cache_control.max_age = 3600 * 24  # 1 dia
            response.cache_control.public = True
            response.cache_control.immutable = True     # adiciona o immutable
            response.set_etag(etag_value)

            # Torna a resposta condicional
            response.make_conditional(request)

            return response
        else:
            return send_file('static/img/page.png', mimetype='image/jpeg'),503

    except Exception:
        return send_file('static/img/page.png', mimetype='image/jpeg'),503



@site.route('/img/page/proxy')
def pageproxy():
        # Recupera a URL remota via query string
    url = request.args.get('url')
    return proxy(url)



@site.route('/img/cover/<uuid>')
def coverproxy(uuid):
    size = request.args.get("size")
    url = manga.id2Cover(uuid)
    if size is not None:
        url += f".{size}.jpg"
    return proxy(url)


#routes

@site.route('/')
@site.route('/index')
def home():
    """
    listar recomendados, recentes, ...
    """
    # Definindo a chave do cache para `dall`
    cache_key = 'home_page'

    # Tenta pegar o conteúdo de `dall` do cache
    dall = cache.get(cache_key)
    
    # Se não estiver no cache, gera o conteúdo e coloca no cache
    if dall is None:
        dall = {}
        r = manga.recentes()
        dall[r['tag']] = r['itens']
        for i in range(3):
            c = manga.choiceTags()
            dall[c['tag']] = c['itens']
        
        # Armazena `dall` no cache por 5 minutos
        cache.set(cache_key, dall, timeout=1800)  # timeout=300 para 5 minutos

    if current_user.is_authenticated:
        d = {
            "Lidos Recentemente":manga.continuar_lendo(0),
            "Favoritos":manga.lista_ultimos_favoritos(0)   
        }
    else:
        d = {}

    return render_template('index.html',data=dall,user_data=d)


@site.route('/cap/<cap_id>')
def mangaCap(cap_id):
    """
    ler capitulos especifico
    """

    dall = manga.getChapter(cap_id)

    return render_template('cap.html',data=dall)


@site.route('/cap/<cap_id>/readed')
@login_required
def mangaCapReaded(cap_id):
    """
        lista de lidos
    """
    if current_user.is_authenticated:
        data = manga.getChapter(cap_id)

        m = Manga.query.filter_by(uuid=data['manga_id']).first()

        if not m:
            m = Manga(
                uuid=uuid.UUID(data['manga_id']),
                title=data['manga']
            )
            db.session.add(m)
            db.session.commit()

        c = Chapter.query.filter_by(uuid=cap_id).first()

        if not c:
            c = Chapter(
                uuid=cap_id,
                manga_id=m.id
            )
            db.session.add(c)
            db.session.commit()

        read = Readed.query.filter_by(
            user_id=current_user.id,
            chapter_id=c.id
        ).first()

        if read:
            read.updated_at = datetime.utcnow()
            db.session.commit()

        else:
            read = Readed(
                user_id=current_user.id,
                chapter_id=c.id
            )
            db.session.add(read)
            db.session.commit()

        response = {
            "status": "success",
            "message": "Request was successful"
        }
        
        # Retornando o JSON com o status 200 (default)
        return jsonify(response)
    
    response = {
        "status": "error",
        "message": "Unauthorized access"
    }
    return jsonify(response), 401
        

@site.route('/mangas',defaults={'page':1})
@site.route('/mangas/<int:page>')
def mangaList(page):
    """
    grid com todos os mangás
    """
    page = 0 if page <= 0 else page-1
    offset = manga.limit * (page)

    dall = manga.listaGeral(offset)
        
    return render_template('list.html',data=dall,page=page,paginator=True)

@site.route('/manga/<manga_id>')
def manga_sinopse(manga_id):
    """
    abre um titulo especifico
    """
    dall = manga.showManga(manga_id)

    return render_template('manga.html', data=dall)


@site.route('/manga/<manga_id>/favorite')
@login_required
def mangaFav(manga_id):
    if current_user.is_authenticated:
        data = manga.showManga(manga_id=manga_id)

        m = Manga.query.filter_by(uuid=data['id']).first()

        if not m:
            m = Manga(
                uuid=data['id'],
                title=data['title']
            )
            db.session.add(m)
            db.session.commit()

        favorite = Favorite.query.filter_by(user_id=current_user.id,manga_id=m.id).first()
        if not favorite:
            status = "added"
            favorite = Favorite(
                user_id=current_user.id,
                manga_id=m.id
            )
            db.session.add(favorite)
            db.session.commit()
        else:
            status = "deleted"
            db.session.delete(favorite)
            db.session.commit()
        
        response = {
            "status": "success",
            "message": status
        }
        
        # Retornando o JSON com o status 200 (default)
        return jsonify(response)
    
    response = {
        "status": "error",
        "message": "Unauthorized access"
    }
    return jsonify(response), 401


@site.route('/search',defaults={'page':1},methods=["GET","POST"])
@site.route('/search/<int:page>')
def searchTitles(page):
    if g.form.validate_on_submit():
        page = 0 if page <= 0 else page-1
        offset = manga.limit * (page)

        search_query = g.form.query.data

        dall = manga.searchMangaByTitle(search_query)
            
        return render_template('list.html',data=dall,page=page,paginator=False)
    else:
        return redirect(url_for('user.mangaList'))

