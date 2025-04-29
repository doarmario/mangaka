from flask import Flask

def create_app():
    app = Flask(__name__)

    from app.routes.manga_routes import site

    app.register_blueprint(site)

    return app
    