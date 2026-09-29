"""Internal manga-api-v1 service; no user credentials or browser required."""
from flask import Flask, Response, jsonify, request

from .client import MangaFire, SourceError, checked_url


def create_app(service=None):
    app = Flask(__name__)
    service = service or MangaFire()
    app.extensions['mangafire'] = service

    @app.errorhandler(SourceError)
    def source_error(error):
        response = jsonify(source='mangafire', error=str(error))
        response.status_code = error.status
        if error.retry_after:
            response.headers['Retry-After'] = str(error.retry_after)
        return response

    @app.before_request
    def source():
        if request.args.get('source', 'mangafire') != 'mangafire':
            raise SourceError('Unknown source.', 400)

    def payload(data):
        return jsonify(source='mangafire', **data)

    def page_number(maximum):
        try:
            page = int(request.args.get('page', '1'))
        except ValueError:
            raise SourceError('Invalid page.', 400) from None
        if not 1 <= page <= maximum:
            raise SourceError('Page is outside the supported range.', 400)
        return page

    @app.get('/api/health')
    def health():
        return payload({'status': 'ok'})

    def listing():
        query = ' '.join(request.args.get('q', '').split())
        if len(query) > 120:
            raise SourceError('Search query is too long.', 400)
        return payload(service.listing(page_number(10000), query or None, request.args.get('tag') or None))

    app.add_url_rule('/api/manga/catalog', 'catalog', listing)
    app.add_url_rule('/api/manga/search', 'search', listing)

    @app.get('/api/manga/tags')
    def tags():
        return payload({'tags': service.tags()})

    @app.get('/api/manga/<hid>')
    def info(hid):
        return payload(service.info(hid))

    @app.get('/api/manga/<hid>/chapters')
    def chapters(hid):
        return payload(service.chapters(hid, request.args.get('lang', 'en'), page_number(100)))

    @app.get('/api/manga/<hid>/chapters/<chapter>/pages')
    def pages(hid, chapter):
        return payload(service.pages(hid, chapter))

    @app.get('/api/proxy/image')
    def image():
        url = checked_url(request.args.get('url', ''), image=True)
        body, content_type = service.transport.get(url, image=True)
        return Response(body, content_type=content_type, headers={
            'Cache-Control': 'public, max-age=3600', 'X-Content-Type-Options': 'nosniff'})

    return app
