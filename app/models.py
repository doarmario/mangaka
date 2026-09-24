from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import UserMixin
from datetime import datetime, timezone
from uuid import uuid4
from . import db, bcrypt


def utc_now():
    """Return a naive UTC timestamp for legacy database DateTime columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)

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

    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    updated_at = db.Column(db.DateTime, default=utc_now, onupdate=utc_now, nullable=False)

class SourceReference(db.Model):
    """Stable local IDs keep provider slugs out of existing UUID columns."""
    id = db.Column(db.String(36), primary_key=True)
    source = db.Column(db.String(32), nullable=False)
    kind = db.Column(db.String(16), nullable=False)
    remote_id = db.Column(db.Text, nullable=False)
    parent_id = db.Column(db.String(36), nullable=True, index=True)
    payload = db.Column(db.JSON, nullable=False, default=dict)


class UpdateNotification(db.Model):
    __table_args__ = (db.UniqueConstraint('user_id', 'chapter_uuid', name='uq_notification_user_chapter'),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    manga_uuid = db.Column(db.String(36), nullable=False)
    manga_title = db.Column(db.String(255), nullable=False)
    chapter_uuid = db.Column(db.String(255), nullable=False)
    chapter_label = db.Column(db.String(80), nullable=False)
    source_name = db.Column(db.String(80), nullable=False)
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    read_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship('User', backref=db.backref('update_notifications', lazy='dynamic'))


class WorkerStatus(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    last_run_at = db.Column(db.DateTime, nullable=True)
    last_success_at = db.Column(db.DateTime, nullable=True)
    last_created = db.Column(db.Integer, nullable=False, default=0)
    last_error = db.Column(db.Text, nullable=True)
