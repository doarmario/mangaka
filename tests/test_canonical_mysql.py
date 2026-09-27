"""Opt-in real MySQL checks. Only a disposable canonical_test database is accepted."""
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import pytest
from sqlalchemy import text
from app import create_app, db
from app.models import Work, SourceWork, WorkAlias
from app.libs.canonical import resolve_work
from conftest import TestConfig

pytestmark = pytest.mark.skipif(not os.environ.get('MANGAKA_TEST_MYSQL_URL'), reason='requires disposable MySQL')


@pytest.fixture
def mysql_app():
    from sqlalchemy.engine import make_url
    uri = os.environ['MANGAKA_TEST_MYSQL_URL']
    assert make_url(uri).database == 'canonical_test', 'Refusing a non-test database'
    class Config(TestConfig):
        SQLALCHEMY_DATABASE_URI = uri
    app = create_app(Config)
    with app.app_context():
        db.create_all()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


def test_mysql_concurrent_first_discovery(mysql_app):
    barrier = Barrier(4)
    def discover(index):
        with mysql_app.app_context():
            barrier.wait(timeout=10)
            row = resolve_work({'id': 'source-' + str(index % 2), 'title': 'Concurrent Story'}, 'provider-' + str(index % 2))
            db.session.commit()
            return row.work_id
    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = list(pool.map(discover, range(4)))
    assert len(set(ids)) == 1
    with mysql_app.app_context():
        assert Work.query.count() == 1
        assert SourceWork.query.count() == 2
        assert WorkAlias.query.count() == 1


def test_mysql_migration_old_schema(mysql_app):
    # Same real migration and preservation assertions as the SQLite test.
    from test_canonical import test_migration_old_schema_roundtrip
    test_migration_old_schema_roundtrip(mysql_app)
