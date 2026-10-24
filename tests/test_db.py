"""Database schema migrations."""

from __future__ import annotations

import sqlite3

from lector.db import Database


def test_existing_database_gets_open_count_column(tmp_path):
    path = tmp_path / "lector.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE books (book_id TEXT PRIMARY KEY)")

    db = Database(path)
    db.init_schema()

    columns = {
        row["name"] for row in db.query("PRAGMA table_info(books)")
    }
    assert "open_count" in columns
