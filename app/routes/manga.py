from flask import Blueprint, render_template, redirect, url_for,flash
from flask_login import login_user
from app.models import User
from app import db, login_manager

site = Blueprint('user', __name__)


#index 
@site.route('/')
@site.route('/index')
def home():
    """
    listar recomendados, recentes, ...
    """
    return render_template('index.html')

@site.route('/cap')
def mangaCap():
    """
    ler capitulos especifico
    """
    return render_template('cap.html')

@site.route('/mangas')
def mangaList():
    """
    grid com todos os mangás
    """
    return render_template('list.html')

@site.route('/manga/<nome_manga>')
def manga_sinopse(nome_manga):
    """
    abre um titulo especifico
    """
    return render_template('manga.html', nome_manga=nome_manga)
