"""add background update notifications

Revision ID: 20260924_update_notifications
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = '20260924_update_notifications'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # init-db uses SQLAlchemy create_all for fresh installations. If it has
    # already created this table, only record the migration as applied.
    if 'update_notification' in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        'update_notification',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('manga_uuid', sa.String(length=36), nullable=False),
        sa.Column('manga_title', sa.String(length=255), nullable=False),
        sa.Column('chapter_uuid', sa.String(length=255), nullable=False),
        sa.Column('chapter_label', sa.String(length=80), nullable=False),
        sa.Column('source_name', sa.String(length=80), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('read_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_update_notification_user_id', 'update_notification', ['user_id'])


def downgrade():
    op.drop_index('ix_update_notification_user_id', table_name='update_notification')
    op.drop_table('update_notification')
