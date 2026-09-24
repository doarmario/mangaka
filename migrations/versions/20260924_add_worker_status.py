"""add worker health status

Revision ID: 20260924_worker_status
Revises: 20260924_update_notifications
"""
from alembic import op
import sqlalchemy as sa

revision = '20260924_worker_status'
down_revision = '20260924_update_notifications'
branch_labels = None
depends_on = None


def upgrade():
    if 'worker_status' in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        'worker_status',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('last_run_at', sa.DateTime(), nullable=True),
        sa.Column('last_success_at', sa.DateTime(), nullable=True),
        sa.Column('last_created', sa.Integer(), nullable=False),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade():
    op.drop_table('worker_status')
