from flask import abort
from flask import make_response, current_app, send_from_directory
from mangadex.errors import ApiError
from flask import Blueprint, render_template, redirect, url_for,flash,send_file, Response, request, stream_with_context, jsonify, g
from flask_login import login_user,current_user,logout_user, login_required

from app.models import User, Manga, Favorite, Readed, Chapter, UpdateNotification, WorkerStatus, utc_now

from app.libs.library import Library as Mangas
from app.libs.manga_novel import MangaNovel, SourceUnavailable
from app.libs.source_registry import definitions, supports_tags, package_errors

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
from sqlalchemy.exc import SQLAlchemyError

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
    g.tag_sources = {key: label for key, label in g.sources.items() if supports_tags(key)}
    g.catalog_sources = {'all': 'All sources', **g.sources}
    g.selected_source = manga.selected_source()
    g.unread_notifications = 0
    if current_user.is_authenticated:
        try:
            g.unread_notifications = UpdateNotification.query.filter_by(
                user_id=current_user.id, read_at=None).count()
        except SQLAlchemyError:
            # Keep login and the rest of the site usable while an older
            # installation is applying the notification migrations.
            db.session.rollback()


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
            return send_from_directory(current_app.static_folder, 'img/cover-placeholder.svg', mimetype='image/svg+xml'),503

    except Exception:
        return send_from_directory(current_app.static_folder, 'img/cover-placeholder.svg', mimetype='image/svg+xml'),503



@site.route('/img/page/proxy')
def pageproxy():
        # Recupera a URL remota via query string
    url = request.args.get('url')
    return proxy(url)



@site.route('/img/cover/<uuid>')
def coverproxy(uuid):
    size = request.args.get("size")
    if size not in (None, "256", "512"):
        return 'Invalid cover size', 400
    url = manga.id2Cover(uuid, size=size)
    if url.startswith("/static/"):
        return redirect(url)
    # MangaDex cover URLs are already public, immutable CDN assets. Let the
    # browser fetch them directly because some self-hosted Docker networks
    # cannot reliably reach uploads.mangadex.org from the web container.
    if url.startswith('https://uploads.mangadex.org/covers/'):
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
            'Recently read':manga.continuar_lendo(0),
            'Favorites':manga.lista_ultimos_favoritos(0),
            'Updates':manga.favorite_updates(20),
        }
    else:
        d = {}

    return render_template('index.html',data=dall,user_data=d)


@site.route('/status')
def status():
    checks = []
    try:
        db.session.execute(text('SELECT 1'))
        checks.append({'name': 'Database', 'state': 'ok', 'detail': 'Connected'})
    except Exception:
        checks.append({'name': 'Database', 'state': 'error', 'detail': 'Unavailable'})
    try:
        probe = 'mangaka_status_probe'
        cache.set(probe, True, timeout=10)
        checks.append({'name': 'Cache', 'state': 'ok' if cache.get(probe) else 'error', 'detail': 'Redis is running'})
    except Exception:
        checks.append({'name': 'Cache', 'state': 'error', 'detail': 'Unavailable'})
    for definition in definitions().values():
        if not definition.visible or not definition.enabled or definition.adapter == 'mangadex':
            continue
        name = definition.name
        api_url = definition.endpoint(current_app.config)
        if api_url:
            try:
                response = requests.get(f'{api_url}/api/health', timeout=(1, 3))
                checks.append({'name': name, 'state': 'ok' if response.ok else 'error',
                               'detail': 'Connected' if response.ok else f'HTTP {response.status_code}'})
            except requests.RequestException:
                checks.append({'name': name, 'state': 'error', 'detail': 'Unavailable'})
        else:
            checks.append({'name': name, 'state': 'warning', 'detail': 'Not configured'})
    worker = db.session.get(WorkerStatus, 1)
    checks.append({'name': 'Update worker',
                   'state': 'warning' if worker is None or worker.last_success_at is None else 'ok',
                   'detail': 'Waiting for the first run' if worker is None or worker.last_success_at is None
                   else f'Last run: {worker.last_success_at.strftime("%Y-%m-%d %H:%M")}'})
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
    from app.models import ReadingProgress
    shelves = ReadingProgress.query.filter_by(user_id=current_user.id).order_by(ReadingProgress.last_read_at.desc()).all()
    return render_template('library.html', shelves=shelves,
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

    from app.models import ReadingProgress
    dall['resume_page'] = request.args.get('page', type=int)
    if dall['resume_page'] is None and current_user.is_authenticated:
        progress = ReadingProgress.query.filter_by(user_id=current_user.id, work_id=dall['work_id']).first()
        if progress and progress.last_source_chapter_id == cap_id:
            dall['resume_page'] = progress.page_number
        elif progress and progress.logical_chapter_id == dall['logical_chapter_id']:
            from app.libs.identity import approximate_page
            dall['resume_page'] = approximate_page(progress.progress_percent, len(dall.get('pages', [])))
    dall['resume_page'] = max(1, min(dall['resume_page'] or 1, max(1, len(dall.get('pages', [])))))
    return render_template('cap.html',data=dall)


@site.route('/cap/<cap_id>/readed')
@login_required
def mangaCapReaded(cap_id):
    from app.libs.reading import save_progress
    from app.models import SourceChapter
    data = manga.getChapter(cap_id)
    count = len(data.get('pages', []))
    save_progress(current_user.id, db.session.get(SourceChapter, cap_id), max(1, count), count, completed=True)
    return jsonify(status='success', message='Request was successful')


@site.route('/cap/<cap_id>/progress', methods=['POST'])
@login_required
def chapter_progress(cap_id):
    from app.models import SourceChapter
    from app.libs.reading import save_progress
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        abort(400, 'Invalid reading progress.')
    page, count = data.get('page'), data.get('page_count')
    if type(page) is not int or type(count) is not int or not 1 <= page <= count <= 10000:
        abort(400, 'Invalid page.')
    sc = db.session.get(SourceChapter, cap_id)
    if sc is None:
        manga.getChapter(cap_id)
        sc = db.session.get(SourceChapter, cap_id)
    progress = save_progress(current_user.id, sc, page, count, completed=page == count)
    return jsonify(status='success', work_id=progress.work_id, progress_percent=progress.progress_percent)


@site.route('/work/<work_id>')
def work_detail(work_id):
    from app.libs.canonical import canonical_work
    work = canonical_work(work_id)
    if work is None:
        abort(404)
    return render_template('manga.html', data=manga.work_details(work))


@site.route('/api/works/<work_id>')
def work_metadata(work_id):
    from app.libs.canonical import canonical_work
    from app.models import ReadingProgress
    work = canonical_work(work_id)
    if work is None:
        abort(404)
    progress = (ReadingProgress.query.filter_by(user_id=current_user.id, work_id=work.id).first()
                if current_user.is_authenticated else None)
    response = jsonify(id=work.id, title=work.canonical_title,
        aliases=[alias.alias for alias in work.aliases],
        titles=work.metadata_json.get('titles', []),
        sources=[{'id': source.id, 'source': source.source,
                  'available': source.available and source.source in manga.sources(),
                  'url': url_for('user.manga_sinopse', manga_id=source.id)} for source in work.sources],
        reading_progress={'chapter_key': progress.logical_chapter.chapter_key if progress.logical_chapter else None,
                          'logical_chapter_id': progress.logical_chapter_id,
                          'progress_percent': progress.progress_percent, 'status': progress.status,
                          'last_source': progress.last_source} if progress else None)
    response.headers['Cache-Control'] = 'private, no-store'
    return response


@site.route('/work/<work_id>/continue')
@login_required
def continue_work(work_id):
    from app.libs.canonical import canonical_work
    from app.libs.reading import resolve_source_for_chapter
    work = canonical_work(work_id)
    if work is None:
        abort(404)
    chapter, page = resolve_source_for_chapter(current_user.id, work, manga)
    return redirect(url_for('user.mangaCap', cap_id=chapter.id, page=page))


@site.route('/work/<work_id>/status', methods=['POST'])
@login_required
def reading_status(work_id):
    from app.models import ReadingProgress
    from app.libs.canonical import canonical_work
    from app.libs.reading import STATUSES
    work = canonical_work(work_id)
    if work is None:
        abort(404)
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        abort(400)
    status = payload.get('status')
    if not isinstance(status, str) or status not in STATUSES:
        abort(400)
    from app.libs.canonical import lock_catalog
    lock_catalog()
    progress = ReadingProgress.query.filter_by(user_id=current_user.id, work_id=work.id).first()
    if progress is None:
        progress = ReadingProgress(user_id=current_user.id, work_id=work.id)
        db.session.add(progress)
    progress.status = status
    db.session.commit()
    return jsonify(status='success')


def unified_listing(page, query=None):
    from app.libs.catalog import UnifiedCatalog
    page = max(1, min(page, 500))
    if request.args.get('load') != 'sync':
        return render_template('list.html', data=[], query=query, progressive=True,
                               filters=catalog_filters(), paginator={'page': page, 'total': None,
                               'total_pages': None, 'active': False, 'has_next': False})
    result = UnifiedCatalog(manga).listing(query, page)
    return render_template('list.html', data=result['itens'], query=query,
                           unavailable=result['unavailable'], filters=catalog_filters(),
                           paginator={'page': page, 'total': None, 'total_pages': None,
                                      'active': page > 1 or result['has_next'], 'has_next': result['has_next']})


@site.route('/api/catalog/stream')
def catalog_stream():
    import json
    from app.libs.catalog import UnifiedCatalog
    page = max(1, min(request.args.get('page', 1, type=int), 500))
    query = ' '.join(request.args.get('query', '').split())[:120] or None
    # Cards and navigation belong to the combined catalog regardless of defaults.
    g.selected_source = 'all'

    @stream_with_context
    def events():
        yield json.dumps({'started': True}) + '\n'
        try:
            for result in UnifiedCatalog(manga).iter_listing(query, page):
                if result.get('waiting'):
                    yield json.dumps(result) + '\n'
                    continue
                html = render_template('_catalog_results.html', data=result['itens'], query=query,
                    filters={}, paginator={'page': page, 'total_pages': None,
                    'active': page > 1 or result['has_next'], 'has_next': result['has_next']}) if result['itens'] or result['done'] else None
                yield json.dumps({key: value for key, value in {**result, 'html': html}.items()
                                  if key != 'itens'}) + '\n'
        except SourceUnavailable as exc:
            yield json.dumps({'error': str(exc), 'done': True}) + '\n'
        except Exception:
            current_app.logger.exception('Progressive catalog failed')
            db.session.rollback()
            yield json.dumps({'error': 'Could not finish loading the catalog. Please try again.', 'done': True}) + '\n'

    return Response(events(), mimetype='application/x-ndjson', headers={
        'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no',
        'Content-Encoding': 'identity',
    })


@site.route('/manga/<manga_id>/sources')
def manga_sources(manga_id):
    from app.libs.catalog import UnifiedCatalog
    result = UnifiedCatalog(manga).alternatives(manga_id)
    return jsonify({**result, 'sources': [{**source, 'url': url_for('user.manga_sinopse', manga_id=source['id'])}
                                        for source in result['sources']]})


def catalog_tag():
    tag_id = request.args.get('tag', '').strip()
    if not tag_id:
        return None
    if g.selected_source == 'mangadex':
        tags = manga.listTags()
    elif supports_tags(g.selected_source):
        tags = MangaNovel(g.selected_source).tags()
    else:
        abort(400, 'This source does not support genre filters yet.')
    tag = next((item for item in tags if item['id'] == tag_id), None)
    if not tag:
        abort(404, 'Tag not found in this source.')
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
    elif supports_tags(g.selected_source):
        available = MangaNovel(g.selected_source).tags()
    else:
        abort(400, 'This source does not support tags.')
    available = sorted(available, key=lambda item: str(item.get('name', '')).casefold())
    return render_template('tags.html', tags=available)


@site.route('/mangas',defaults={'page':1})
@site.route('/mangas/<int:page>')
def mangaList(page):
    """
    grid com todos os mangás
    """

    if g.selected_source == 'all':
        return unified_listing(page)
    tag = catalog_tag()
    filters = catalog_filters()
    active_filters = {key: value for key, value in filters.items() if value}
    if g.selected_source != 'mangadex':
        page = max(1, min(page, 500))
        result = MangaNovel(g.selected_source).catalog(page, tag=tag)
        total = result['total']
        page = result.get('page', page)
        total_pages = result.get('total_pages', max(1, ceil(total / manga.limit)) if total is not None else None)
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
    from app.libs.reading import PROVIDER_ERRORS
    from app.models import SourceWork
    try:
        dall = manga.showManga(manga_id)
    except PROVIDER_ERRORS:
        source_work = db.session.get(SourceWork, manga_id)
        if source_work is None:
            raise
        source_work.available = False
        db.session.commit()
        dall = manga.work_details(source_work.work)
    return render_template('manga.html', data=dall)


@site.route('/manga/<manga_id>/favorite')
@login_required
def mangaFav(manga_id):
    from app.libs.canonical import canonical_work
    from app.models import SourceWork
    from app.libs.reading import toggle_favorite
    work = canonical_work(manga_id)
    sw = next(iter(work.sources), None) if work else db.session.get(SourceWork, manga_id)
    if sw is None:
        data = manga.showManga(manga_id)
        sw = db.session.get(SourceWork, data['id'])
    return jsonify(status='success', message=toggle_favorite(current_user.id, sw))


@site.route('/search', defaults={'page': 1}, methods=["GET"])
@site.route('/search/<int:page>', methods=["GET"])
def searchTitles(page):
    if g.selected_source == 'all':
        query = ' '.join(request.args.get('query', '').split())[:120]
        if not query:
            return redirect(url_for('user.mangaList', source='all'))
        return unified_listing(page, query)
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
            if g.selected_source != 'mangadex' or 'source' in request.args:
                params['source'] = g.selected_source
            if tag:
                params['tag'] = tag
            return redirect(url_for('user.mangaList', **params))

        page = max(1, min(page, 10000 // manga.limit))
        offset = manga.limit * (page - 1)
        if g.selected_source != 'mangadex':
            dall = MangaNovel(g.selected_source).search(query, page, tag=tag)
            total = dall['total']
            page = dall.get('page', page)
            total_pages = dall.get('total_pages', max(1, ceil(total / manga.limit)) if total is not None else None)
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
        if g.selected_source != 'mangadex' or 'source' in request.args:
            params['source'] = g.selected_source
        if tag:
            params['tag'] = tag
        return redirect(url_for('user.mangaList', **params))




@site.errorhandler(ApiError)
def mangadex_error(error):
    status = 503 if str(error.code) == "429" else 502
    response = make_response('MangaDex is currently unavailable. Please try again later.', status)
    return response


@site.errorhandler(requests.RequestException)
def mangadex_network_error(error):
    return 'Could not connect to MangaDex. Please try again later.', 503


@site.errorhandler(SourceUnavailable)
def source_unavailable(error):
    return render_template('source_error.html', message=str(error)), 503


@site.route("/sources")
def sources_page():
    return render_template("sources.html", source_definitions=definitions().values(),
                           package_errors=package_errors())
