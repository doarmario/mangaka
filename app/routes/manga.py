from flask import abort
from flask import make_response, current_app, send_from_directory
from mangadex.errors import ApiError
from flask import Blueprint, render_template, redirect, url_for,flash,send_file, Response, request, stream_with_context, jsonify, g
from flask_login import login_user,current_user,logout_user, login_required

from app.models import User, Manga, Favorite, Readed, Chapter, UpdateNotification, WorkerStatus, utc_now

from app.libs.library import Library as Mangas
from app.libs.manga_novel import MangaNovel, SourceUnavailable

from app.forms import SearchForm

from app import db, login_manager
from app import cache


from math import ceil
from io import BytesIO

import requests
import hashlib
import time
import uuid
from sqlalchemy import text

site = Blueprint('user', __name__)

header = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36 Mangaka/1.0',
    'Referer': 'https://mangadex.org/'
}

manga = Mangas()


@site.before_request
def before_request():
    g.form = SearchForm()
    g.sources = manga.sources()
    g.selected_source = manga.selected_source()
    g.unread_notifications = 0
    if current_user.is_authenticated:
        g.unread_notifications = UpdateNotification.query.filter_by(
            user_id=current_user.id, read_at=None).count()


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
        r = session.get(url, headers=header, timeout=(5, 20))

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
    if size not in (None, "256", "512"):
        return "Tamanho de capa inválido", 400
    url = manga.id2Cover(uuid, size=size)
    if url.startswith("/static/"):
        return redirect(url)
    return proxy(url)


#routes

@site.route('/')
@site.route('/index')
def home():
    """
    listar recomendados, recentes, ...
    """
    # Definindo a chave do cache para `dall`
    cache_key = manga._key('home')

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
            "Favoritos":manga.lista_ultimos_favoritos(0),
            "Novidades":manga.favorite_updates(20),
        }
    else:
        d = {}

    return render_template('index.html',data=dall,user_data=d)


@site.route('/status')
def status():
    checks = []
    try:
        db.session.execute(text('SELECT 1'))
        checks.append({'name': 'Banco de dados', 'state': 'ok', 'detail': 'Conectado'})
    except Exception:
        checks.append({'name': 'Banco de dados', 'state': 'error', 'detail': 'Indisponível'})
    try:
        probe = 'mangaka_status_probe'
        cache.set(probe, True, timeout=10)
        checks.append({'name': 'Cache', 'state': 'ok' if cache.get(probe) else 'error', 'detail': 'Redis ativo'})
    except Exception:
        checks.append({'name': 'Cache', 'state': 'error', 'detail': 'Indisponível'})
    api_url = current_app.config.get('MANGA_NOVEL_API_URL', '').rstrip('/')
    if api_url:
        try:
            response = requests.get(f'{api_url}/api/health', timeout=(1, 3))
            checks.append({'name': 'API de fontes', 'state': 'ok' if response.ok else 'error',
                           'detail': 'Conectada' if response.ok else f'HTTP {response.status_code}'})
        except requests.RequestException:
            checks.append({'name': 'API de fontes', 'state': 'error', 'detail': 'Indisponível'})
    else:
        checks.append({'name': 'API de fontes', 'state': 'warning', 'detail': 'Não configurada'})
    worker = db.session.get(WorkerStatus, 1)
    checks.append({'name': 'Worker de novidades',
                   'state': 'warning' if worker is None or worker.last_success_at is None else 'ok',
                   'detail': 'Aguardando primeira execução' if worker is None or worker.last_success_at is None
                   else f'Última execução: {worker.last_success_at.strftime("%d/%m/%Y %H:%M")}'})
    return render_template('status.html', checks=checks, worker=worker)


@site.route('/service-worker.js')
def service_worker():
    response = send_from_directory(current_app.static_folder, 'sw.js', mimetype='application/javascript')
    response.headers['Service-Worker-Allowed'] = '/'
    response.headers['Cache-Control'] = 'no-cache'
    return response


@site.route('/biblioteca')
@login_required
def library():
    return render_template('library.html',
                           recent=manga.continuar_lendo(0),
                           favorites=manga.lista_ultimos_favoritos(0),
                           updates=manga.favorite_updates(20))


@site.route('/novidades')
@login_required
def updates():
    return render_template('updates.html', updates=manga.favorite_updates(50))


@site.route('/notificacoes')
@login_required
def notifications():
    source = request.args.get('source', '').strip()
    query = UpdateNotification.query.filter_by(user_id=current_user.id)
    if source:
        query = query.filter_by(source_name=source)
    entries = query.order_by(
        UpdateNotification.created_at.desc()).limit(100).all()
    sources = [name for (name,) in db.session.query(UpdateNotification.source_name).filter_by(
        user_id=current_user.id).distinct().order_by(UpdateNotification.source_name).all()]
    return render_template('notifications.html', notifications=entries, sources=sources, selected_source=source)


@site.route('/notificacoes/atualizar')
@login_required
def notifications_refresh():
    from app.update_worker import refresh_once
    refresh_once(user_id=current_user.id)
    return redirect(url_for('user.notifications'))


@site.route('/notificacoes/marcar-todas', methods=['POST'])
@login_required
def notifications_mark_all():
    UpdateNotification.query.filter_by(user_id=current_user.id, read_at=None).update(
        {'read_at': utc_now()}, synchronize_session=False)
    db.session.commit()
    return redirect(url_for('user.notifications'))


@site.route('/api/notificacoes/count')
@login_required
def notifications_count():
    count = UpdateNotification.query.filter_by(user_id=current_user.id, read_at=None).count()
    return jsonify({'count': count})


@site.route('/notificacoes/<int:notification_id>/read', methods=['POST'])
@login_required
def notification_read(notification_id):
    entry = UpdateNotification.query.filter_by(id=notification_id, user_id=current_user.id).first_or_404()
    entry.read_at = utc_now()
    db.session.commit()
    return jsonify({'status': 'success'})


@site.route('/cap/<cap_id>')
def mangaCap(cap_id):
    """
    ler capitulos especifico
    """

    dall = manga.getChapter(cap_id)
    notification_id = request.args.get('notification', type=int)
    if current_user.is_authenticated and notification_id:
        entry = UpdateNotification.query.filter_by(id=notification_id, user_id=current_user.id).first()
        if entry and entry.read_at is None:
            entry.read_at = utc_now()
            db.session.commit()

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
                uuid=data['manga_id'],
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
            read.updated_at = utc_now()
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
        

def catalog_tag():
    tag_id = request.args.get('tag', '').strip()
    if not tag_id:
        return None
    if g.selected_source == 'mangadex':
        tags = manga.listTags()
    elif g.selected_source == 'asura':
        tags = MangaNovel('asura').tags()
    else:
        abort(400, 'Esta fonte ainda não oferece filtro por gênero.')
    tag = next((item for item in tags if item['id'] == tag_id), None)
    if not tag:
        abort(404, 'Tag não encontrada nesta fonte.')
    g.selected_tag = tag
    return tag_id


def catalog_filters():
    allowed_languages = {'pt-br', 'pt', 'en'}
    allowed_statuses = {'ongoing', 'completed', 'hiatus', 'cancelled'}
    language = request.args.get('language', '').strip().lower()
    status = request.args.get('status', '').strip().lower()
    return {
        'language': language if language in allowed_languages else None,
        'status': status if status in allowed_statuses else None,
    }


@site.route('/tags')
def tags():
    """List every tag available for the currently selected provider."""
    if g.selected_source == 'mangadex':
        available = manga.listTags()
    elif g.selected_source == 'asura':
        available = MangaNovel('asura').tags()
    else:
        abort(400, 'Esta fonte não oferece tags.')
    available = sorted(available, key=lambda item: str(item.get('name', '')).casefold())
    return render_template('tags.html', tags=available)


@site.route('/mangas',defaults={'page':1})
@site.route('/mangas/<int:page>')
def mangaList(page):
    """
    grid com todos os mangás
    """

    tag = catalog_tag()
    filters = catalog_filters()
    active_filters = {key: value for key, value in filters.items() if value}
    if g.selected_source != 'mangadex':
        page = max(1, min(page, 500))
        result = MangaNovel(g.selected_source).catalog(page, tag=tag)
        total = result['total']
        total_pages = max(1, ceil(total / manga.limit)) if total is not None else None
        return render_template('list.html', data=result['itens'], filters=filters,
                               paginator={'page': page, 'total': total, 'total_pages': total_pages,
                                          'active': page > 1 or result['has_next'], 'has_next': result['has_next']})

    total = manga.listMangaByTag(tag, 0, **active_filters)['total'] if tag else manga.getTotalPages(**active_filters)
    max_pages = max(1, ceil(min(total, 10000) / manga.limit))
    rpage = max(1, min(page, max_pages))
    offset = manga.limit * (rpage - 1)
    dall = manga.listMangaByTag(tag, offset, **active_filters) if tag else manga.listaGeral(offset, **active_filters)
    paginator = {"page": rpage, "offset": offset, "total": dall["total"],
                 "total_pages": max_pages, "active": max_pages > 1}

    return render_template('list.html', data=dall["itens"], filters=filters, paginator=paginator)

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


@site.route('/search', defaults={'page': 1}, methods=["GET"])
@site.route('/search/<int:page>', methods=["GET"])
def searchTitles(page):
    tag = catalog_tag()
    filters = catalog_filters()
    active_filters = {key: value for key, value in filters.items() if value}
    form = SearchForm(request.args)
    if form.validate():
        # Collapse repeated whitespace so equivalent searches share cache keys
        # and produce stable pagination URLs.
        query = ' '.join(form.query.data.split())[:120]
        if not query:
            params = {}
            if g.selected_source != 'mangadex':
                params['source'] = g.selected_source
            if tag:
                params['tag'] = tag
            return redirect(url_for('user.mangaList', **params))

        page = max(1, min(page, 10000 // manga.limit))
        offset = manga.limit * (page - 1)
        if g.selected_source != 'mangadex':
            dall = MangaNovel(g.selected_source).search(query, page, tag=tag)
            total = dall['total']
            total_pages = max(1, ceil(total / manga.limit)) if total is not None else None
            return render_template('list.html', data=dall['itens'], query=query, filters=filters,
                                   paginator={'page': page, 'total': total, 'total_pages': total_pages,
                                              'active': page > 1 or dall['has_next'], 'has_next': dall['has_next']})
        dall = manga.searchMangaByTitle(query, offset, tag=tag, **active_filters)

        paginator = {
            "page": page,
            "offset": offset,
            "total": dall["total"],
            "total_pages": max(1, ceil(min(dall["total"], 10000) / manga.limit)),
            "active": dall["total"] > manga.limit
        }

        return render_template(
            'list.html',
            form=form, filters=filters,
            data=dall['itens'],
            paginator=paginator,
            query=query
        )
    else:
        # Keep the selected provider when a malformed/blank query is submitted.
        params = {}
        if g.selected_source != 'mangadex':
            params['source'] = g.selected_source
        if tag:
            params['tag'] = tag
        return redirect(url_for('user.mangaList', **params))




@site.errorhandler(ApiError)
def mangadex_error(error):
    status = 503 if str(error.code) == "429" else 502
    response = make_response("MangaDex indisponível no momento. Tente novamente mais tarde.", status)
    return response


@site.errorhandler(requests.RequestException)
def mangadex_network_error(error):
    return "Não foi possível conectar ao MangaDex. Tente novamente mais tarde.", 503


@site.errorhandler(SourceUnavailable)
def source_unavailable(error):
    return render_template('source_error.html', message=str(error)), 503
