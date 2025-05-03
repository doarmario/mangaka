from flask import Blueprint, render_template, redirect, url_for,flash,send_file, Response, request, stream_with_context
from flask_login import login_user,current_user,logout_user

from app.models import User
from app import db, login_manager
from app import manga
from app import cache

from io import BytesIO

import requests

site = Blueprint('user', __name__)

header = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36 Mangaka/1.0',
    'Referer': 'https://mangadex.org/',  # Ajuste para a URL de origem do Mangaka, se necessário
}


# Função para gerar chave de cache única por usuário
def get_cache_key():
    """Gera uma chave de cache única por usuário"""
    if current_user.is_authenticated:
        return f"mangaka_user_loged_home"  # Chave única para cada usuário autenticado
    
    return 'home_page'  # Caso não esteja logado, usa uma chave global



@site.route('/img/page/proxy')
def proxy():
    # Recupera a URL remota via query string
    url = request.args.get('url')
    if not url:
        return "Faltando parâmetro 'url'", 400

    try:
        r = requests.get(url, headers=header)

        if r.status_code == 200:
            response = send_file(BytesIO(r.content), mimetype='image/jpeg')

            # Configura os cabeçalhos de cache para o lado do cliente
            response.cache_control.max_age = 800  # Tempo máximo de cache (em segundos)
            response.cache_control.public = True   # O conteúdo pode ser armazenado em cache publicamente

            return response
        else:
            # Em caso de erro na requisição, envia a imagem estática
            response = send_file('static/img/page.png', mimetype='image/jpeg')
            return response

    except Exception as e:
        # Em caso de erro na requisição, envia a imagem estática
        response = send_file('static/img/page.png', mimetype='image/jpeg')
        return response



@site.route('/img/cover/<uuid>')
@cache.cached(timeout=86400)
def covers(uuid):
    try:
        url = manga.cover2id(uuid)
        r = requests.get(url,headers=header)

        if r.status_code == 200:
            resp = send_file(BytesIO(r.content), mimetype='image/jpeg')
            # Configura os cabeçalhos de cache para o lado do cliente
            resp.cache_control.max_age = 604800  # Tempo máximo de cache (em segundos)
            resp.cache_control.public = True   # O conteúdo pode ser armazenado em cache publicamente
            return resp
    except: #deve ter um metodo melhor de fazer isso!
        return send_file('static/img/page.png', mimetype='image/jpeg')



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
        cache.set(cache_key, dall, timeout=600)  # timeout=300 para 5 minutos


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
        cache.set(cache_key,dall,timeout=800)

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
