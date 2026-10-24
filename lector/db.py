"""SQLite persistence.

The database is the single source of truth for metadata, reading progress and
the short-code index.  Parsed content and audio live on the filesystem; only
what needs to be queried lives here.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS books (
    book_id        TEXT PRIMARY KEY,
    title          TEXT NOT NULL,
    author         TEXT,
    language       TEXT,
    sha256         TEXT NOT NULL UNIQUE,
    size_bytes     INTEGER NOT NULL,
    cover_path     TEXT,
    chapter_count  INTEGER NOT NULL DEFAULT 0,
    sentence_count INTEGER NOT NULL DEFAULT 0,
    word_count     INTEGER NOT NULL DEFAULT 0,
    open_count     INTEGER NOT NULL DEFAULT 0,
    voice_id       TEXT,
    tts_state      TEXT NOT NULL DEFAULT 'pending',
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chapters (
    book_id       TEXT NOT NULL,
    chapter_id    TEXT NOT NULL,
    idx           INTEGER NOT NULL,
    title         TEXT NOT NULL,
    sentence_count INTEGER NOT NULL DEFAULT 0,
    word_count    INTEGER NOT NULL DEFAULT 0,
    char_count    INTEGER NOT NULL DEFAULT 0,
    audio_duration REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (book_id, chapter_id)
);

CREATE TABLE IF NOT EXISTS sentences (
    book_id       TEXT NOT NULL,
    sentence_id   TEXT NOT NULL,
    chapter_id    TEXT NOT NULL,
    chapter_index INTEGER NOT NULL,
    chapter_title TEXT NOT NULL DEFAULT '',
    block_id      TEXT NOT NULL,
    sent_index    INTEGER NOT NULL,
    ord           INTEGER NOT NULL DEFAULT 0,
    char_count    INTEGER NOT NULL DEFAULT 0,
    text          TEXT NOT NULL,
    PRIMARY KEY (book_id, sentence_id)
);

CREATE INDEX IF NOT EXISTS idx_sentences_order
    ON sentences (book_id, chapter_index, sent_index);

CREATE TABLE IF NOT EXISTS progress (
    book_id      TEXT PRIMARY KEY,
    chapter_id   TEXT,
    sentence_id  TEXT,
    word_index   INTEGER,
    percent      REAL NOT NULL DEFAULT 0.0,
    updated_at   TEXT NOT NULL,
    updated_by   TEXT NOT NULL DEFAULT 'api',
    device_label TEXT
);

CREATE TABLE IF NOT EXISTS short_codes (
    code        TEXT PRIMARY KEY,
    book_id     TEXT NOT NULL,
    chapter_id  TEXT NOT NULL,
    sentence_id TEXT NOT NULL,
    word_index  INTEGER,
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_short_codes_cursor
    ON short_codes (book_id, chapter_id, sentence_id, word_index);

CREATE TABLE IF NOT EXISTS audio_tiles (
    book_id     TEXT NOT NULL,
    sentence_id TEXT NOT NULL,
    cache_key   TEXT NOT NULL,
    voice_id    TEXT NOT NULL,
    rate        TEXT NOT NULL,
    duration    REAL NOT NULL,
    granularity TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    PRIMARY KEY (book_id, sentence_id)
);
"""


class Database:
    """Thread-safe handle to the SQLite file.

    FastAPI runs sync endpoints in a worker thread pool, so each thread gets
    its own connection.
    """

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._local = threading.local()
        self._write_lock = threading.Lock()

    def connect(self) -> sqlite3.Connection:
        """Return this thread's connection, opening it on first use."""
        conn = getattr(self._local, "conn", None)
        if conn is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self.path, timeout=30.0, isolation_level=None)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA synchronous=NORMAL")
            self._local.conn = conn
        return conn

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    @contextmanager
    def write(self) -> Iterator[sqlite3.Connection]:
        """Run a write transaction, serialised across threads."""
        conn = self.connect()
        with self._write_lock:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
            except Exception:
                conn.execute("ROLLBACK")
                raise
            else:
                conn.execute("COMMIT")

    def init_schema(self) -> None:
        conn = self.connect()
        with self._write_lock:
            conn.executescript(SCHEMA)
            columns = {
                row["name"] for row in conn.execute("PRAGMA table_info(books)").fetchall()
            }
            if "open_count" not in columns:
                conn.execute(
                    "ALTER TABLE books ADD COLUMN open_count INTEGER NOT NULL DEFAULT 0"
                )

    def query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        return list(self.connect().execute(sql, params).fetchall())

    def query_one(self, sql: str, params: tuple = ()) -> sqlite3.Row | None:
        cur = self.connect().execute(sql, params)
        return cur.fetchone()
