import sys
import os
from dotenv import load_dotenv

path = 'config/.env'  #try .path[0] if 1 doesn't work
load_dotenv(path)

# Verifique se a variável DATABASE_URL está sendo carregada
print("DATABASE_URL:", os.getenv('DATABASE_URL'))  # Adicione este print para depuração

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "default-secret-key")
    SQLALCHEMY_DATABASE_URI = os.getenv("SQLALCHEMY_DATABASE_URI")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    HOST = '0.0.0.0'
    DEBUG = os.getenv("DEBUG", "False").lower() in ["true", "1"]
    ENV = os.getenv("FLASK_ENV", "production")
    # Configuração do Flask-Login
    LOGIN_VIEW = 'auth.login'  # Define qual rota será usada para login (exemplo: 'auth.login')
    SESSION_PROTECTION = 'strong'  # Proteção de sessão