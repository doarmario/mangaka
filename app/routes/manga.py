from flask import Blueprint, render_template

site = Blueprint('user', __name__)

@site.route('/')
@site.route('/index')
def home():
    return render_template('index.html')

@site.route('/cap')
def mangaCap():
    return render_template('cap.html')

@site.route('/mangas')
def mangaList():
    return render_template('list.html')

@site.route('/manga/<nome_manga>')
def manga_sinopse(nome_manga):
    return render_template('manga.html', nome_manga=nome_manga)
