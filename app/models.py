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
    work_id = db.Column(db.String(36), db.ForeignKey('work.id'), nullable=True, index=True)
    work = db.relationship('Work')
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    manga_id = db.Column(db.Integer, db.ForeignKey('manga.id'), nullable=False)
    chapter_id = db.Column(db.Integer, db.ForeignKey('chapter.id'), nullable=True)

    user = db.relationship('User', back_populates='favorites')
    manga = db.relationship('Manga', back_populates='favorites')
    chapter = db.relationship('Chapter', back_populates='favorites')

class Readed(db.Model):
    work_id = db.Column(db.String(36), db.ForeignKey('work.id'), nullable=True, index=True)
    logical_chapter_id = db.Column(db.String(36), db.ForeignKey('logical_chapter.id'), nullable=True, index=True)
    page_number = db.Column(db.Integer, nullable=False, default=1, server_default='1')
    page_count = db.Column(db.Integer, nullable=False, default=0, server_default='0')
    progress_percent = db.Column(db.Float, nullable=False, default=0, server_default='0')
    completed = db.Column(db.Boolean, nullable=False, default=True, server_default='1')
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
    work_id = db.Column(db.String(36), db.ForeignKey('work.id'), nullable=True, index=True)
    logical_chapter_id = db.Column(db.String(36), db.ForeignKey('logical_chapter.id'), nullable=True, index=True)
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


class CatalogLock(db.Model):
    """Short database mutex for identity decisions, never held over HTTP calls."""
    id = db.Column(db.Integer, primary_key=True)
    version = db.Column(db.Integer, nullable=False, default=0)


class Work(db.Model):
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid4()))
    canonical_title = db.Column(db.String(255), nullable=False)
    normalized_title = db.Column(db.Text, nullable=False)
    metadata_json = db.Column(db.JSON, nullable=False, default=dict)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    updated_at = db.Column(db.DateTime, nullable=False, default=utc_now, onupdate=utc_now)
    sources = db.relationship('SourceWork', back_populates='work')
    aliases = db.relationship('WorkAlias', back_populates='work')


class WorkAlias(db.Model):
    __table_args__ = (db.UniqueConstraint('work_id', 'alias_hash', name='uq_work_alias'),)
    id = db.Column(db.Integer, primary_key=True)
    work_id = db.Column(db.String(36), db.ForeignKey('work.id'), nullable=False, index=True)
    alias = db.Column(db.Text, nullable=False)
    normalized_alias = db.Column(db.Text, nullable=False)
    alias_hash = db.Column(db.String(64), nullable=False, index=True)
    origin = db.Column(db.String(32))
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    work = db.relationship('Work', back_populates='aliases')


class WorkExternalID(db.Model):
    __table_args__ = (db.UniqueConstraint('provider', 'external_id', name='uq_work_external_id'),)
    id = db.Column(db.Integer, primary_key=True)
    work_id = db.Column(db.String(36), db.ForeignKey('work.id'), nullable=False, index=True)
    provider = db.Column(db.String(32), nullable=False)
    external_id = db.Column(db.String(255), nullable=False)


class SourceWork(db.Model):
    __table_args__ = (db.UniqueConstraint('source', 'external_hash', name='uq_source_work_remote'),)
    # Existing local source UUID, retained as a compatibility URL identifier.
    id = db.Column(db.String(36), primary_key=True)
    work_id = db.Column(db.String(36), db.ForeignKey('work.id'), nullable=False, index=True)
    source = db.Column(db.String(32), nullable=False)
    external_id = db.Column(db.Text, nullable=False)
    external_hash = db.Column(db.String(64), nullable=False)
    source_url = db.Column(db.Text)
    title_at_source = db.Column(db.String(255), nullable=False)
    normalized_title = db.Column(db.Text, nullable=False)
    available = db.Column(db.Boolean, nullable=False, default=True)
    last_seen_at = db.Column(db.DateTime)
    last_success_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    updated_at = db.Column(db.DateTime, nullable=False, default=utc_now, onupdate=utc_now)
    work = db.relationship('Work', back_populates='sources')


class LogicalChapter(db.Model):
    __table_args__ = (db.UniqueConstraint('work_id', 'key_hash', name='uq_logical_chapter'),)
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid4()))
    work_id = db.Column(db.String(36), db.ForeignKey('work.id'), nullable=False, index=True)
    chapter_key = db.Column(db.Text, nullable=False)
    key_hash = db.Column(db.String(64), nullable=False)
    chapter_number = db.Column(db.Numeric(24, 8))
    volume_number = db.Column(db.String(80))
    label = db.Column(db.String(255), nullable=False)
    title = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    updated_at = db.Column(db.DateTime, nullable=False, default=utc_now, onupdate=utc_now)


class SourceChapter(db.Model):
    __table_args__ = (db.UniqueConstraint('source_work_id', 'external_hash', name='uq_source_chapter_remote'),)
    id = db.Column(db.String(36), primary_key=True)
    source_work_id = db.Column(db.String(36), db.ForeignKey('source_work.id'), nullable=False, index=True)
    logical_chapter_id = db.Column(db.String(36), db.ForeignKey('logical_chapter.id'), nullable=False, index=True)
    external_id = db.Column(db.Text, nullable=False)
    external_hash = db.Column(db.String(64), nullable=False)
    source_url = db.Column(db.Text)
    number_at_source = db.Column(db.String(255))
    title = db.Column(db.Text)
    language = db.Column(db.String(16))
    available = db.Column(db.Boolean, nullable=False, default=True)
    last_seen_at = db.Column(db.DateTime)
    last_success_at = db.Column(db.DateTime)
    source_work = db.relationship('SourceWork')
    logical_chapter = db.relationship('LogicalChapter')


class ReadingProgress(db.Model):
    __table_args__ = (db.UniqueConstraint('user_id', 'work_id', name='uq_progress_user_work'),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    work_id = db.Column(db.String(36), db.ForeignKey('work.id'), nullable=False, index=True)
    logical_chapter_id = db.Column(db.String(36), db.ForeignKey('logical_chapter.id'), nullable=True)
    page_number = db.Column(db.Integer, nullable=False, default=1)
    page_count = db.Column(db.Integer, nullable=False, default=0)
    progress_percent = db.Column(db.Float, nullable=False, default=0)
    last_source = db.Column(db.String(32))
    last_source_chapter_id = db.Column(db.String(36))
    started_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    last_read_at = db.Column(db.DateTime, nullable=False, default=utc_now)
    completed_at = db.Column(db.DateTime)
    status = db.Column(db.String(20), nullable=False, default='reading')
    work = db.relationship('Work')
    logical_chapter = db.relationship('LogicalChapter')
