import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient

from app import db
from app.main import app, get_conn


@pytest.fixture
def conn(tmp_path):
    path = tmp_path / "test.db"
    db.init_db(path)
    c = db.connect(path)
    yield c
    c.close()


@pytest.fixture
def client(tmp_path):
    path = tmp_path / "api.db"
    db.init_db(path)

    def override():
        c = db.connect(path)
        try:
            yield c
        finally:
            c.close()

    app.dependency_overrides[get_conn] = override
    yield TestClient(app)
    app.dependency_overrides.clear()
