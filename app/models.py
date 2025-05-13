from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import UserMixin
from datetime import datetime
from uuid import uuid4
from . import db, bcrypt

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)

    favorites = db.relationship('Favorite', back_populates='user')
    read_chapters = db.relationship('Readed', back_populates='user')

    def get_id(self):
        return str(self.id)

    def set_password(self, password):
        """Usando bcrypt para hash de senha"""
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        """Verificando a senha usando bcrypt"""
        return bcrypt.check_password_hash(self.password_hash, password)

class Manga(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, default=lambda: str(uuid4()))
    title = db.Column(db.String(255), nullable=False)

    chapters = db.relationship('Chapter', back_populates='manga')
    favorites = db.relationship('Favorite', back_populates='manga')

class Chapter(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, default=lambda: str(uuid4()))
    manga_id = db.Column(db.Integer, db.ForeignKey('manga.id'), nullable=False)

    manga = db.relationship('Manga', back_populates='chapters')
    read_chapters = db.relationship('Readed', back_populates='chapter')
    favorites = db.relationship('Favorite', back_populates='chapter')

class Favorite(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    manga_id = db.Column(db.Integer, db.ForeignKey('manga.id'), nullable=False)
    chapter_id = db.Column(db.Integer, db.ForeignKey('chapter.id'), nullable=True)

    user = db.relationship('User', back_populates='favorites')
    manga = db.relationship('Manga', back_populates='favorites')
    chapter = db.relationship('Chapter', back_populates='favorites')

class Readed(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    chapter_id = db.Column(db.Integer, db.ForeignKey('chapter.id'), nullable=False)

    user = db.relationship('User', back_populates='read_chapters')
    chapter = db.relationship('Chapter', back_populates='read_chapters')

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)