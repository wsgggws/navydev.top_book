"""Bounded local shelf snapshots, isolated by server and credentials."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

from lector_tui import cache

MAX_SHELF_BYTES = 2 * 1024 * 1024


def valid_books(books) -> bool:
    return isinstance(books, list) and len(books) <= 10000 and all(
        isinstance(book, dict)
        and isinstance(book.get("book_id"), str)
        and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", book["book_id"])
        and isinstance(book.get("title"), str)
        and len(book["title"]) <= 4096
        and (book.get("author") is None or isinstance(book["author"], str))
        for book in books
    )


class ShelfCache:
    def __init__(self, base_url: str, token: str = "", *, root: Path | None = None):
        key = f"{base_url.rstrip('/')}\0{token}".encode()
        self.path = (root or cache.CACHE_DIR / "shelves") / (hashlib.sha256(key).hexdigest() + ".json")

    def get(self) -> list[dict] | None:
        try:
            with self.path.open("rb") as handle:
                data = handle.read(MAX_SHELF_BYTES + 1)
            if len(data) > MAX_SHELF_BYTES:
                return None
            payload = json.loads(data)
            books = payload.get("books") if isinstance(payload, dict) and payload.get("version") == 1 else None
            return books if valid_books(books) else None
        except (OSError, ValueError, UnicodeError):
            return None

    def put(self, books: list[dict]) -> None:
        if not valid_books(books):
            return
        data = json.dumps({"version": 1, "books": books}, ensure_ascii=False).encode()
        if len(data) > MAX_SHELF_BYTES:
            return
        temporary = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # NamedTemporaryFile creates a private file (0600), even before the
            # atomic rename. Credentials only contribute to the hashed filename.
            with tempfile.NamedTemporaryFile(dir=self.path.parent, delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(data)
            os.replace(temporary, self.path)
        except OSError:
            pass
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
