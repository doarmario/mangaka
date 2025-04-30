from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, BooleanField, EmailField
from wtforms.validators import DataRequired, Email, EqualTo, Length

class LoginForm(FlaskForm):
    login = StringField('Login', validators=[DataRequired(), Email()])  # E-mail ou Nome de Usuário
    password = PasswordField('Password', validators=[DataRequired(), Length(min=6)])  # Senha
    remember_me = BooleanField('Lembrar de mim')  # Lembrar de mim
    submit = SubmitField('Login')  # Botão de Login


class RegisterForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    email = EmailField('E-mail', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    password_repeat = PasswordField('Repeat password', validators=[DataRequired(), EqualTo('password', message='As senhas devem ser iguais.')])
