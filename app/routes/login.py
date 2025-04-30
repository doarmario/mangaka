from flask import Blueprint, render_template,redirect,url_for,request,flash

from flask_login import login_user, login_required, logout_user, current_user
from sqlalchemy import or_
from app.models import User

from markupsafe import escape

from app import db, bcrypt,login_manager
from app.forms import LoginForm,RegisterForm

auth = Blueprint('auth', __name__)

@auth.route('/', methods=['GET', 'POST'])
@auth.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:  # Verifica se o usuário já está logado
        return redirect(url_for('user.home'))  # Redireciona para a home

    form = LoginForm()

    if form.validate_on_submit():  # Se o formulário for válido
        login = form.login.data  # Obtém o valor do campo de login
        password = form.password.data  # Obtém o valor do campo de senha

        # Buscando o usuário no banco de dados, considerando username ou email
        user = User.query.filter(
            or_(
                User.username == login,  # Verifica username
                User.email == login  # Verifica email
            )
        ).first()

        if user and bcrypt.check_password_hash(user.password, password):  # Verifica a senha com bcrypt
            login_user(user, remember=form.remember_me.data)  # Realiza o login
            flash("Login bem-sucedido!", 'success')
            return redirect(url_for('user.home'))  # Redireciona para a home do usuário
        else:
            flash('Falha no login. Verifique suas credenciais.', 'danger')

    return render_template('login.html', form=form)

@auth.route('/logout')
@login_required
def logout():
    logout_user()
    flash("logout.",'info')
    return redirect(url_for('auth.login'))


@auth.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        hashed_pw = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        user = User(username=form.username.data, email=form.email.data, password=hashed_pw)
        db.session.add(user)
        db.session.commit()
        flash('Conta criada com sucesso! Faça login.', 'success')
        return redirect(url_for('auth.login'))
    return render_template('register.html', form=form)


