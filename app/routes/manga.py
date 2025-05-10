from flask import Blueprint, render_template, redirect, url_for,flash,send_file, Response, request, stream_with_context
from flask_login import login_user,current_user,logout_user

from app.models import User
from app.libs.md import Mangas

from app import db, login_manager
from app import cache

from io import BytesIO

import requests
import hashlib
import time

site = Blueprint('user', __name__)

header = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36 Mangaka/1.0',
    'Referer': 'https://mangadex.org/'
}

manga = Mangas()


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
        r = session.get(url,headers=header)

        if r.status_code == 200:
            response = send_file(BytesIO(r.content), mimetype='image/jpeg')

            # Cabeçalhos de cache
            response.cache_control.max_age = 800  # Tempo máximo de cache (em segundos)
            response.cache_control.public = True   # O conteúdo pode ser armazenado em cache publicamente

            # Adiciona cabeçalhos 'ETag' e 'Last-Modified' para controle de cache
            last_modified = time.gmtime()  # Você pode calcular isso com base na data de modificação real
            response.last_modified = last_modified
            response.set_etag(Etag(url))  # Geração de um ETag único (pode ser um hash do conteúdo)
            
            return response
        else:
            print("error 200")
            # Em caso de erro na requisição, envia a imagem estática
            response = send_file('static/img/page.png', mimetype='image/jpeg')
            return response

    except Exception as e:
        print("Erro:",e)
        # Em caso de erro na requisição, envia a imagem estática
        response = send_file('static/img/page.png', mimetype='image/jpeg')
        return response


@site.route('/img/page/proxy')
def pageproxy():
        # Recupera a URL remota via query string
    url = request.args.get('url')
    return proxy(url)



@site.route('/img/cover/<uuid>')
def coverproxy(uuid):
    url = manga.id2Cover(uuid)
    return proxy(url)


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
        cache.set(cache_key, dall, timeout=900)  # timeout=300 para 5 minutos


    return render_template('index.html',data=dall)

@site.route('/cap/<cap_id>')
def mangaCap(cap_id):
    """
    ler capitulos especifico
    """
    cache_key = f'cap_page_{cap_id}'

    # Tenta pegar o conteúdo de `dall` do cache
    dall = cache.get(cache_key)
    
    if dall is None:
        dall = manga.getChapter(cap_id)
        cache.set(cache_key,dall,timeout=900)

    return render_template('cap.html',data=dall)

@site.route('/mangas',defaults={'page':1})
@site.route('/mangas/<int:page>')
def mangaList(page):
    """
    grid com todos os mangás
    """
    page = 0 if page <= 0 else page-1
    offset = manga.limit * (page)

    cache_key = f"manga_page_{page}"

     # Tenta pegar o conteúdo de `dall` do cache
    dall = cache.get(cache_key)

    if dall is None:
        dall = manga.listaGeral(offset)
        
        # Armazena `dall` no cache por 5 minutos
        cache.set(cache_key, dall, timeout=3600)  # timeout=300 para 5 minutos

    return render_template('list.html',data=dall,page=page)

@site.route('/manga/<manga_id>')
def manga_sinopse(manga_id):
    """
    abre um titulo especifico
    """
    cache_key = f"manga_info_{manga_id}"

    dall = cache.get(cache_key)
    if dall is None:
        dall = manga.showManga(manga_id)
        cache.set(cache_key,dall,timeout=900)

    return render_template('manga.html', data=dall)
