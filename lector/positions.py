"""The cursor: the one and only position representation.

Reading, listening, following, sharing and resuming all project this single
value.  Nothing else in the system is allowed to invent a position.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass

#: Crockford Base32 without the letters that look like numbers.
CROCKFORD_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

#: Length of a share code.
SHORT_CODE_LENGTH = 8


@dataclass(frozen=True)
class Cursor:
    """A position in a book."""

    book_id: str
    chapter_id: str
    sentence_id: str
    word_index: int | None = None

    def same_place(self, other: "Cursor | None") -> bool:
        """True when both cursors point at exactly the same place."""
        if other is None:
            return False
        return (
            self.book_id == other.book_id
            and self.chapter_id == other.chapter_id
            and self.sentence_id == other.sentence_id
            and self.word_index == other.word_index
        )


def encode_cursor(cursor: Cursor) -> str:
    """Encode a cursor into one compact, URL-safe string."""
    word = "" if cursor.word_index is None else str(cursor.word_index)
    return f"{cursor.book_id}:{cursor.chapter_id}:{cursor.sentence_id}:{word}"


def decode_cursor(text: str) -> Cursor | None:
    """Decode a cursor, returning ``None`` when the string is malformed."""
    parts = text.split(":")
    if len(parts) != 4:
        return None
    book_id, chapter_id, sentence_id, word = parts
    if not book_id or not chapter_id or not sentence_id:
        return None
    word_index: int | None = None
    if word:
        try:
            word_index = int(word)
        except ValueError:
            return None
    return Cursor(
        book_id=book_id,
        chapter_id=chapter_id,
        sentence_id=sentence_id,
        word_index=word_index,
    )


def generate_short_code(length: int = SHORT_CODE_LENGTH) -> str:
    """A random share code."""
    return "".join(secrets.choice(CROCKFORD_ALPHABET) for _ in range(length))


def is_valid_short_code(code: str) -> bool:
    """True when the code uses only Crockford Base32 characters."""
    return bool(code) and len(code) == SHORT_CODE_LENGTH and all(
        char in CROCKFORD_ALPHABET for char in code.upper()
    )


def normalize_short_code(code: str) -> str:
    """Upper-case a code and map the excluded letters onto their look-alikes."""
    table = {"I": "1", "L": "1", "O": "0", "U": "V"}
    return "".join(table.get(char, char) for char in code.upper())


def clamp_percent(value: float) -> float:
    """Keep a percentage inside ``[0, 1]``."""
    return max(0.0, min(1.0, float(value)))
