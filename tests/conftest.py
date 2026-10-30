import pytest

from core.db import Database
from core.retrieval import load_tracks


@pytest.fixture
def catalogue():
    return load_tracks()


@pytest.fixture
def database(tmp_path, catalogue):
    db = Database(tmp_path / "test.sqlite3")
    db.seed_tracks(catalogue)
    return db
