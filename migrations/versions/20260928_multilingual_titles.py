"""Preserve known raw titles and language/source provenance in work metadata.

Revision ID: 20260928_multilingual_titles
Revises: 20260928_canonical_reading
"""
from alembic import op
import sqlalchemy as sa
from app.libs.identity import title_variants

revision = '20260928_multilingual_titles'
down_revision = '20260928_canonical_reading'
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    metadata = sa.MetaData()
    work = sa.Table('work', metadata, autoload_with=connection)
    alias = sa.Table('work_alias', metadata, autoload_with=connection)
    source_work = sa.Table('source_work', metadata, autoload_with=connection)
    reference = sa.Table('source_reference', metadata, autoload_with=connection)
    known = {}
    for row in connection.execute(sa.select(alias)).mappings():
        known.setdefault(row['work_id'], []).extend(title_variants(
            {'title': row['alias']}, row['origin']))
    query = sa.select(source_work.c.work_id, source_work.c.source, reference.c.payload).join(
        reference, reference.c.id == source_work.c.id)
    for row in connection.execute(query).mappings():
        known.setdefault(row['work_id'], []).extend(title_variants(row['payload'] or {}, row['source']))
    for row in connection.execute(sa.select(work)).mappings():
        info = dict(row['metadata_json'] or {})
        info['titles'] = title_variants({'titles': [*info.get('titles', []), *known.get(row['id'], [])]})
        connection.execute(work.update().where(work.c.id == row['id']).values(metadata_json=info))


def downgrade():
    # Additional JSON metadata is backwards compatible; never discard titles.
    pass
