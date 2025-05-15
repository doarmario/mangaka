import redis
import sys
import os
from dotenv import load_dotenv

path = '.env'  #try .path[0] if 1 doesn't work
load_dotenv(path)

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "default-secret-key")

    # Agora você pode acessar as variáveis de ambiente usando os comandos os.getenv()
    DB_HOST = os.getenv('DB_HOST')
    DB_USER = os.getenv('DB_USER')
    DB_PASSWORD = os.getenv('DB_PASSWORD')
    DB_NAME = os.getenv('DB_NAME')

    # Conexão com o banco de dados, por exemplo, com SQLAlchemy
    SQLALCHEMY_DATABASE_URI = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:3306/{DB_NAME}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    DEBUG = os.getenv("DEBUG", "False").lower() in ["true", "1"]
    ENV = os.getenv("FLASK_ENV", "production")

    # Configuração do Flask-Login
    LOGIN_VIEW = 'auth.login'  # Define qual rota será usada para login (exemplo: 'auth.login')
    SESSION_PROTECTION = 'strong'  # Proteção de sessão

    #cache
    CACHE_TYPE = "redis"
    CACHE_REDIS_URL = os.getenv('REDIS_HOST_CACHE')
    CACHE_DEFAULT_TIMEOUT = 3600
    CACHE_REDIS_TIMEOUT = 5
    CACHE_REDIS_SOCKET_TIMEOUT = 10


    #session
    SESSION_TYPE = "redis"
    SESSION_PREMANENT = False
    SESSION_USE_SIGNER = True
    SESSION_KEY_PREFIX = "mangaka_"
    SESSION_REDIS = redis.from_url(os.getenv('REDIS_HOST_SESSION'))
    

    #
    COMPRESS_MIMETYPE = ['*/*']