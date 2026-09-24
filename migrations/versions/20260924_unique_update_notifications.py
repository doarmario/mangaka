"""prevent duplicate notifications per user and chapter

Revision ID: 20260924_unique_notifications
Revises: 20260924_worker_status
"""
from alembic import op
import sqlalchemy as sa

revision = '20260924_unique_notifications'
down_revision = '20260924_worker_status'
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    constraints = inspector.get_unique_constraints('update_notification')
    if not any(item.get('name') == 'uq_notification_user_chapter' for item in constraints):
        op.create_unique_constraint('uq_notification_user_chapter', 'update_notification', ['user_id', 'chapter_uuid'])


def downgrade():
    op.drop_constraint('uq_notification_user_chapter', 'update_notification', type_='unique')
