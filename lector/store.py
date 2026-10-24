"""The bridge between the database and the filesystem.

Metadata, progress and the search index live in SQLite; the original EPUB,
the parsed chapters and the audio tiles live on disk because they are large
and rarely joined against.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lector.config import Settings
from lector.db import Database
from lector.epub.parse import ParsedBook, ParsedChapter, ParsedTocNode, parse_epub
from lector.models import Block, Book, Chapter, Sentence, TocNode

#: The book id is derived from the content hash, which makes uploads idempotent.
BOOK_ID_PREFIX = "b_"


def utcnow() -> str:
    """Current time in the ISO-8601 UTC form the contract uses."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def book_id_for(sha256: str) -> str:
    """The id of the book with this content hash."""
    return f"{BOOK_ID_PREFIX}{sha256[:8]}"


@dataclass
class IngestResult:
    """Outcome of an upload."""

    book: Book
    duplicate: bool


class Store:
    """Everything the API needs to read and write books."""

    def __init__(self, settings: Settings, db: Database) -> None:
        self.settings = settings
        self.db = db

    # -- paths -----------------------------------------------------------
    def book_dir(self, book_id: str) -> Path:
        return self.settings.books_dir / book_id

    def chapter_path(self, book_id: str, chapter_id: str) -> Path:
        return self.book_dir(book_id) / "chapters" / f"{chapter_id}.json"

    def meta_path(self, book_id: str) -> Path:
        return self.book_dir(book_id) / "meta.json"

    def source_path(self, book_id: str) -> Path:
        return self.book_dir(book_id) / "source.epub"

    def cover_path(self, book_id: str) -> Path | None:
        path = self.book_dir(book_id) / "cover.bin"
        return path if path.exists() else None

    # -- ingestion -------------------------------------------------------
    def ingest(
        self,
        data: bytes,
        title: str | None = None,
        author: str | None = None,
        voice_id: str | None = None,
    ) -> IngestResult:
        """Store an uploaded EPUB, or return the existing book for the same bytes."""
        import hashlib

        sha256 = hashlib.sha256(data).hexdigest()
        existing = self.db.query_one("SELECT * FROM books WHERE sha256 = ?", (sha256,))
        if existing is not None:
            return IngestResult(book=self._row_to_book(existing), duplicate=True)

        parsed = parse_epub(data)
        if title:
            parsed.title = title
        if author:
            parsed.author = author

        book_id = book_id_for(sha256)
        target = self.book_dir(book_id)
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        (target / "chapters").mkdir(parents=True, exist_ok=True)
        self.source_path(book_id).write_bytes(data)

        self._write_meta(book_id, parsed)
        for chapter in parsed.chapters:
            self._write_chapter(book_id, chapter)

        now = utcnow()
        with self.db.write() as conn:
            conn.execute(
                """
                INSERT INTO books (book_id, title, author, language, sha256, size_bytes,
                                   cover_path, chapter_count, sentence_count, word_count,
                                   voice_id, tts_state, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    book_id,
                    parsed.title,
                    parsed.author,
                    parsed.language,
                    parsed.sha256,
                    parsed.size_bytes,
                    "cover.bin" if parsed.cover_path else None,
                    len(parsed.chapters),
                    parsed.sentence_count,
                    parsed.word_count,
                    voice_id,
                    "pending",
                    now,
                    now,
                ),
            )
            for chapter in parsed.chapters:
                conn.execute(
                    """
                    INSERT INTO chapters (book_id, chapter_id, idx, title, sentence_count,
                                          word_count, char_count, audio_duration)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        book_id,
                        chapter.id,
                        chapter.index,
                        chapter.title,
                        chapter.sentence_count,
                        chapter.word_count,
                        chapter.char_count,
                        0.0,
                    ),
                )
                order = 0
                for block in chapter.blocks:
                    for sentence in block.sentences:
                        conn.execute(
                            """
                            INSERT INTO sentences (book_id, sentence_id, chapter_id, chapter_index,
                                                   chapter_title, block_id, sent_index, ord,
                                                   char_count, text)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                book_id,
                                sentence.id,
                                chapter.id,
                                chapter.index,
                                chapter.title,
                                block.id,
                                int(sentence.id.rsplit(".s", 1)[1]),
                                order,
                                len(sentence.text),
                                sentence.text,
                            ),
                        )
                        order += 1
        row = self.db.query_one("SELECT * FROM books WHERE book_id = ?", (book_id,))
        assert row is not None
        return IngestResult(book=self._row_to_book(row), duplicate=False)

    def _write_meta(self, book_id: str, parsed: ParsedBook) -> None:
        meta = {
            "title": parsed.title,
            "author": parsed.author,
            "language": parsed.language,
            "sha256": parsed.sha256,
            "size_bytes": parsed.size_bytes,
            "cover": bool(parsed.cover_path),
            "toc": [_toc_to_dict(node) for node in parsed.toc],
        }
        (self.book_dir(book_id) / "meta.json").write_text(
            json.dumps(meta, ensure_ascii=False), "utf-8"
        )
        if parsed.cover_path:
            self._copy_cover(book_id, parsed.cover_path)

    def _copy_cover(self, book_id: str, cover_path: str) -> None:
        import zipfile

        try:
            with zipfile.ZipFile(self.source_path(book_id)) as zf:
                data = zf.read(cover_path)
        except (OSError, KeyError, zipfile.BadZipFile):
            return
        (self.book_dir(book_id) / "cover.bin").write_bytes(data)

    def _write_chapter(self, book_id: str, chapter: ParsedChapter) -> None:
        payload = {
            "chapter_id": chapter.id,
            "index": chapter.index,
            "title": chapter.title,
            "sentence_count": chapter.sentence_count,
            "word_count": chapter.word_count,
            "blocks": [_block_to_dict(block) for block in chapter.blocks],
        }
        path = self.chapter_path(book_id, chapter.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False), "utf-8")

    # -- reading ---------------------------------------------------------
    def get_book_row(self, book_id: str):
        return self.db.query_one("SELECT * FROM books WHERE book_id = ?", (book_id,))

    def get_book(self, book_id: str) -> Book | None:
        row = self.get_book_row(book_id)
        return self._row_to_book(row) if row else None

    def list_books(self, limit: int = 50, offset: int = 0) -> list[Book]:
        """The shelf, with each book's own reading progress."""
        rows = self.db.query(
            """
            SELECT b.*, COALESCE(p.percent, 0) AS progress
            FROM books b
            LEFT JOIN progress p ON p.book_id = b.book_id
            ORDER BY b.updated_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        )
        return [self._row_to_book(row) for row in rows]

    def count_books(self) -> int:
        row = self.db.query_one("SELECT COUNT(*) AS n FROM books")
        return int(row["n"]) if row else 0

    def load_chapter(self, book_id: str, chapter_id: str) -> Chapter | None:
        path = self.chapter_path(book_id, chapter_id)
        if not path.exists():
            return None
        payload = json.loads(path.read_text("utf-8"))
        blocks = [
            Block(
                type=block["type"],
                id=block["id"],
                sentences=[
                    Sentence(
                        id=sentence["id"],
                        text=sentence["text"],
                        char_start=sentence["char_start"],
                        char_end=sentence["char_end"],
                    )
                    for sentence in block["sentences"]
                ],
                anchor=block.get("anchor"),
                anchors=block.get("anchors", []),
                alt=block.get("alt"),
                src=block.get("src"),
            )
            for block in payload["blocks"]
        ]
        return Chapter(
            chapter_id=payload["chapter_id"],
            index=payload["index"],
            title=payload["title"],
            blocks=blocks,
            sentence_count=payload.get("sentence_count", 0),
            word_count=payload.get("word_count", 0),
            audio_duration=0.0,
            tts_state="pending",
        )

    def load_toc(self, book_id: str) -> list[TocNode]:
        path = self.meta_path(book_id)
        if not path.exists():
            return []
        meta = json.loads(path.read_text("utf-8"))
        return [_toc_from_dict(node) for node in meta.get("toc", [])]

    def chapter_ids(self, book_id: str) -> list[str]:
        rows = self.db.query(
            "SELECT chapter_id FROM chapters WHERE book_id = ? ORDER BY idx", (book_id,)
        )
        return [row["chapter_id"] for row in rows]

    def chapter_sentences(self, book_id: str, chapter_id: str) -> list[str]:
        rows = self.db.query(
            """
            SELECT sentence_id FROM sentences
            WHERE book_id = ? AND chapter_id = ?
            ORDER BY chapter_index, ord, sent_index
            """,
            (book_id, chapter_id),
        )
        return [row["sentence_id"] for row in rows]

    def sentence_text(self, book_id: str, sentence_id: str) -> str | None:
        row = self.db.query_one(
            "SELECT text FROM sentences WHERE book_id = ? AND sentence_id = ?",
            (book_id, sentence_id),
        )
        return row["text"] if row else None

    def sentence_chapter(self, book_id: str, sentence_id: str) -> str | None:
        row = self.db.query_one(
            "SELECT chapter_id FROM sentences WHERE book_id = ? AND sentence_id = ?",
            (book_id, sentence_id),
        )
        return row["chapter_id"] if row else None

    def chapter_sentence_order(self, book_id: str, chapter_id: str) -> dict[str, int]:
        """Map every sentence of a chapter to its position."""
        rows = self.db.query(
            """
            SELECT sentence_id FROM sentences
            WHERE book_id = ? AND chapter_id = ?
            ORDER BY chapter_index, ord, sent_index
            """,
            (book_id, chapter_id),
        )
        return {row["sentence_id"]: index for index, row in enumerate(rows)}

    def book_char_total(self, book_id: str) -> int:
        row = self.db.query_one(
            "SELECT COALESCE(SUM(char_count), 0) AS n FROM sentences WHERE book_id = ?",
            (book_id,),
        )
        return int(row["n"]) if row else 0

    def chars_before(self, book_id: str, chapter_id: str, sentence_id: str) -> int:
        """Characters that come before a sentence in the whole book."""
        row = self.db.query_one(
            """
            SELECT COALESCE(SUM(char_count), 0) AS n FROM sentences
            WHERE book_id = ? AND (
                chapter_index < (SELECT chapter_index FROM sentences
                                 WHERE book_id = ? AND sentence_id = ?)
                OR (chapter_index = (SELECT chapter_index FROM sentences
                                     WHERE book_id = ? AND sentence_id = ?)
                    AND ord < (SELECT ord FROM sentences
                               WHERE book_id = ? AND sentence_id = ?))
            )
            """,
            (book_id, book_id, sentence_id, book_id, sentence_id, book_id, sentence_id),
        )
        return int(row["n"]) if row else 0

    def percent_for(self, book_id: str, chapter_id: str, sentence_id: str) -> float:
        """Progress through the book, weighted by character count."""
        total = self.book_char_total(book_id)
        if total <= 0:
            return 0.0
        before = self.chars_before(book_id, chapter_id, sentence_id)
        text = self.sentence_text(book_id, sentence_id) or ""
        return max(0.0, min(1.0, (before + len(text)) / total))

    def delete(self, book_id: str) -> bool:
        """Delete a book with everything that belongs to it."""
        row = self.get_book_row(book_id)
        if row is None:
            return False
        with self.db.write() as conn:
            conn.execute("DELETE FROM sentences WHERE book_id = ?", (book_id,))
            conn.execute("DELETE FROM chapters WHERE book_id = ?", (book_id,))
            conn.execute("DELETE FROM progress WHERE book_id = ?", (book_id,))
            conn.execute("DELETE FROM short_codes WHERE book_id = ?", (book_id,))
            conn.execute("DELETE FROM audio_tiles WHERE book_id = ?", (book_id,))
            conn.execute("DELETE FROM books WHERE book_id = ?", (book_id,))
        shutil.rmtree(self.book_dir(book_id), ignore_errors=True)
        return True

    # -- helpers ---------------------------------------------------------
    def _row_to_book(self, row: Any) -> Book:
        has_cover = bool(row["cover_path"])
        keys = row.keys()
        return Book(
            progress=float(row["progress"]) if "progress" in keys else 0.0,
            book_id=row["book_id"],
            title=row["title"],
            author=row["author"],
            language=row["language"],
            sha256=row["sha256"],
            size_bytes=row["size_bytes"],
            cover_url=(
                f"{self.settings.base_path}/api/v1/books/{row['book_id']}/cover"
                if has_cover
                else None
            ),
            chapter_count=row["chapter_count"],
            sentence_count=row["sentence_count"],
            tts_state=row["tts_state"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


def _block_to_dict(block: Any) -> dict:
    return {
        "type": block.type,
        "id": block.id,
        "anchor": block.anchor,
        "anchors": block.anchors,
        "alt": block.alt,
        "src": block.src,
        "sentences": [
            {
                "id": sentence.id,
                "text": sentence.text,
                "char_start": sentence.char_start,
                "char_end": sentence.char_end,
            }
            for sentence in block.sentences
        ],
    }


def _toc_to_dict(node: ParsedTocNode) -> dict:
    return {
        "id": node.id,
        "title": node.title,
        "chapter_id": node.chapter_id,
        "anchor": node.anchor,
        "children": [_toc_to_dict(child) for child in node.children],
    }


def _toc_from_dict(payload: dict) -> TocNode:
    return TocNode(
        id=payload["id"],
        title=payload["title"],
        chapter_id=payload["chapter_id"],
        anchor=payload.get("anchor"),
        children=[_toc_from_dict(child) for child in payload.get("children", [])],
    )
