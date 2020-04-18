import json

import pytest

from .utils import get_mysql, setup_db, cleanup_db
from webui import app

cfg = json.load(open('config.json'))


@pytest.fixture(scope="function")
def database():
    db = get_mysql()
    setup_db(db)

    cursor = db.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    assert cursor.fetchone() == (0,), "Something went wrong!"
    yield db
    cleanup_db(db)


@pytest.fixture(scope="function")
def client():
    app.config['TESTING'] = True
    client = app.test_client()

    return client
