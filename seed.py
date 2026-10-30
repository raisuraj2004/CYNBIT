"""Seed the local SQLite catalogue from data/tracks.yaml."""

import os
from pathlib import Path

from core.db import Database
from core.retrieval import load_tracks


def seed_database(database_path: Path | None = None) -> None:
    """Insert or update all curated tracks and their skill vocabulary."""
    path = database_path or Path(os.environ.get("BIT_ELEVATE_DB_PATH", "data/pathfinder.sqlite3"))
    Database(path).seed_tracks(load_tracks())


if __name__ == "__main__":
    seed_database()
