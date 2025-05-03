import redis
import sys
import os
from dotenv import load_dotenv

path = '.env'  #try .path[0] if 1 doesn't work
load_dotenv(path)

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "default-secret-key")

    SQLALCHEMY_DATABASE_URI = os.getenv("SQLALCHEMY_DATABASE_URI")
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

    #session
    SESSION_TYPE = "redis"
    SESSION_PREMANENT = False
    SESSION_USE_SIGNER = True
    SESSION_KEY_PREFIX = "mangaka_"
    SESSION_REDIS = os.getenv('REDIS_HOST_SESSION')