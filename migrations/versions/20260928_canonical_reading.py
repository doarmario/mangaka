"""Add canonical works/chapters and backfill without dropping legacy data.

Revision ID: 20260928_canonical_reading
Revises: 20260924_unique_notifications
"""
from alembic import op
import sqlalchemy as sa

revision = '20260928_canonical_reading'
down_revision = '20260924_unique_notifications'
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    tables = sa.inspect(connection).get_table_names()
    if 'catalog_lock' not in tables:
        op.create_table('catalog_lock',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('version', sa.Integer(), nullable=False),
            sa.PrimaryKeyConstraint(*['id']),
        )
    if 'work' not in tables:
        op.create_table('work',
            sa.Column('id', sa.String(length=36), nullable=False),
            sa.Column('canonical_title', sa.String(length=255), nullable=False),
            sa.Column('normalized_title', sa.Text(), nullable=False),
            sa.Column('metadata_json', sa.JSON(), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint(*['id']),
        )
    if 'work_alias' not in tables:
        op.create_table('work_alias',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('work_id', sa.String(length=36), nullable=False),
            sa.Column('alias', sa.Text(), nullable=False),
            sa.Column('normalized_alias', sa.Text(), nullable=False),
            sa.Column('alias_hash', sa.String(length=64), nullable=False),
            sa.Column('origin', sa.String(length=32), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['work_id'], ['work.id']),
            sa.PrimaryKeyConstraint(*['id']),
            sa.UniqueConstraint(*['work_id', 'alias_hash'], name='uq_work_alias'),
        )
        op.create_index('ix_work_alias_work_id', 'work_alias', ['work_id'], unique=False)
        op.create_index('ix_work_alias_alias_hash', 'work_alias', ['alias_hash'], unique=False)
    if 'work_external_id' not in tables:
        op.create_table('work_external_id',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('work_id', sa.String(length=36), nullable=False),
            sa.Column('provider', sa.String(length=32), nullable=False),
            sa.Column('external_id', sa.String(length=255), nullable=False),
            sa.ForeignKeyConstraint(['work_id'], ['work.id']),
            sa.PrimaryKeyConstraint(*['id']),
            sa.UniqueConstraint(*['provider', 'external_id'], name='uq_work_external_id'),
        )
        op.create_index('ix_work_external_id_work_id', 'work_external_id', ['work_id'], unique=False)
    if 'source_work' not in tables:
        op.create_table('source_work',
            sa.Column('id', sa.String(length=36), nullable=False),
            sa.Column('work_id', sa.String(length=36), nullable=False),
            sa.Column('source', sa.String(length=32), nullable=False),
            sa.Column('external_id', sa.Text(), nullable=False),
            sa.Column('external_hash', sa.String(length=64), nullable=False),
            sa.Column('source_url', sa.Text(), nullable=True),
            sa.Column('title_at_source', sa.String(length=255), nullable=False),
            sa.Column('normalized_title', sa.Text(), nullable=False),
            sa.Column('available', sa.Boolean(), nullable=False),
            sa.Column('last_seen_at', sa.DateTime(), nullable=True),
            sa.Column('last_success_at', sa.DateTime(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(['work_id'], ['work.id']),
            sa.PrimaryKeyConstraint(*['id']),
            sa.UniqueConstraint(*['source', 'external_hash'], name='uq_source_work_remote'),
        )
        op.create_index('ix_source_work_work_id', 'source_work', ['work_id'], unique=False)
    if 'logical_chapter' not in tables:
        op.create_table('logical_chapter',
            sa.Column('id', sa.String(length=36), nullable=False),
            sa.Column('work_id', sa.String(length=36), nullable=False),
            sa.Column('chapter_key', sa.Text(), nullable=False),
            sa.Column('key_hash', sa.String(length=64), nullable=False),
            sa.Column('chapter_number', sa.Numeric(precision=24, scale=8), nullable=True),
            sa.Column('volume_number', sa.String(length=80), nullable=True),
            sa.Column('label', sa.String(length=255), nullable=False),
            sa.Column('title', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=False),
            sa.Column('updated_at', sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint(*['id']),
            sa.UniqueConstraint(*['work_id', 'key_hash'], name='uq_logical_chapter'),
            sa.ForeignKeyConstraint(['work_id'], ['work.id']),
        )
        op.create_index('ix_logical_chapter_work_id', 'logical_chapter', ['work_id'], unique=False)
    if 'source_chapter' not in tables:
        op.create_table('source_chapter',
            sa.Column('id', sa.String(length=36), nullable=False),
            sa.Column('source_work_id', sa.String(length=36), nullable=False),
            sa.Column('logical_chapter_id', sa.String(length=36), nullable=False),
            sa.Column('external_id', sa.Text(), nullable=False),
            sa.Column('external_hash', sa.String(length=64), nullable=False),
            sa.Column('source_url', sa.Text(), nullable=True),
            sa.Column('number_at_source', sa.String(length=255), nullable=True),
            sa.Column('title', sa.Text(), nullable=True),
            sa.Column('language', sa.String(length=16), nullable=True),
            sa.Column('available', sa.Boolean(), nullable=False),
            sa.Column('last_seen_at', sa.DateTime(), nullable=True),
            sa.Column('last_success_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint(*['id']),
            sa.ForeignKeyConstraint(['logical_chapter_id'], ['logical_chapter.id']),
            sa.ForeignKeyConstraint(['source_work_id'], ['source_work.id']),
            sa.UniqueConstraint(*['source_work_id', 'external_hash'], name='uq_source_chapter_remote'),
        )
        op.create_index('ix_source_chapter_logical_chapter_id', 'source_chapter', ['logical_chapter_id'], unique=False)
        op.create_index('ix_source_chapter_source_work_id', 'source_chapter', ['source_work_id'], unique=False)
    if 'reading_progress' not in tables:
        op.create_table('reading_progress',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('work_id', sa.String(length=36), nullable=False),
            sa.Column('logical_chapter_id', sa.String(length=36), nullable=True),
            sa.Column('page_number', sa.Integer(), nullable=False),
            sa.Column('page_count', sa.Integer(), nullable=False),
            sa.Column('progress_percent', sa.Float(), nullable=False),
            sa.Column('last_source', sa.String(length=32), nullable=True),
            sa.Column('last_source_chapter_id', sa.String(length=36), nullable=True),
            sa.Column('started_at', sa.DateTime(), nullable=False),
            sa.Column('last_read_at', sa.DateTime(), nullable=False),
            sa.Column('completed_at', sa.DateTime(), nullable=True),
            sa.Column('status', sa.String(length=20), nullable=False),
            sa.UniqueConstraint(*['user_id', 'work_id'], name='uq_progress_user_work'),
            sa.ForeignKeyConstraint(['work_id'], ['work.id']),
            sa.ForeignKeyConstraint(['logical_chapter_id'], ['logical_chapter.id']),
            sa.ForeignKeyConstraint(['user_id'], ['user.id']),
            sa.PrimaryKeyConstraint(*['id']),
        )
        op.create_index('ix_reading_progress_work_id', 'reading_progress', ['work_id'], unique=False)

    additions = {
        'update_notification': [sa.Column('work_id', sa.String(36), nullable=True),
                                sa.Column('logical_chapter_id', sa.String(36), nullable=True)],
        'favorite': [sa.Column('work_id', sa.String(36), nullable=True)],
        'readed': [sa.Column('work_id', sa.String(36), nullable=True),
                   sa.Column('logical_chapter_id', sa.String(36), nullable=True),
                   sa.Column('page_number', sa.Integer(), nullable=False, server_default='1'),
                   sa.Column('page_count', sa.Integer(), nullable=False, server_default='0'),
                   sa.Column('progress_percent', sa.Float(), nullable=False, server_default='0'),
                   sa.Column('completed', sa.Boolean(), nullable=False, server_default='1')],
    }
    for name, columns in additions.items():
        if name not in sa.inspect(connection).get_table_names():
            continue
        existing = {c['name'] for c in sa.inspect(connection).get_columns(name)}
        for column in columns:
            if column.name not in existing:
                with op.batch_alter_table(name) as batch:
                    batch.add_column(column)
                    if column.name in {'work_id', 'logical_chapter_id'}:
                        target = 'work' if column.name == 'work_id' else 'logical_chapter'
                        batch.create_foreign_key('fk_' + name + '_' + column.name, target, [column.name], ['id'])
                        batch.create_index('ix_' + name + '_' + column.name, [column.name])

    # Use the migration connection, not a second transaction/connection from
    # Flask. Backfill performs no network access and leaves every old row intact.
    from app import db
    from app.libs.canonical import backfill
    from sqlalchemy.orm import Session
    original = db.session
    session = Session(bind=connection, join_transaction_mode='create_savepoint')
    try:
        db.session = session
        # Flask-SQLAlchemy Model.query uses the scoped session callable.
        from sqlalchemy.orm import scoped_session
        db.session = scoped_session(lambda: session)
        backfill()
        session.commit()
    finally:
        db.session = original
        session.close()


def downgrade():
    # Non-destructive rollback: preserve canonical-only progress for re-upgrade.
    # Old application versions ignore these additive tables/columns. The
    # previous revision marker is restored by Alembic; no reading data is lost.
    pass
