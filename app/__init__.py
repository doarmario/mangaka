#libs
from flask import Flask

#interno
from app.config import Config
from app.libs.md import Mangas

#extensões
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_bcrypt import Bcrypt
from flask_migrate import Migrate
from flask_caching import Cache
from flask_session import Session

db = SQLAlchemy()
bcrypt = Bcrypt()
csrf = CSRFProtect()
migrate = Migrate()
login_manager = LoginManager()
manga = Mangas()
cache = Cache()
session = Session()

#app
def create_app():

    
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)

    db.init_app(app)
    bcrypt.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app,db)
    cache.init_app(app)
    #session.init_app(app)

    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    from app.routes.manga import site
    from app.routes.login import auth

    app.register_blueprint(site)
    app.register_blueprint(auth,url_prefix='/auth')

    return app
    