"""Metadata rules for books shipped in the repository."""

from __future__ import annotations

import re
from pathlib import Path

_NAME = re.compile(
    r"^(?P<title>.*?)\s*[\(（](?P<author>[^()（）]*)[\)）]\s*$"
)


def metadata_from_filename(path: Path) -> tuple[str, str]:
    """Read ``book_name(author).epub`` metadata from the filename.

    Both ASCII and full-width parentheses are accepted. The filename wins over
    embedded EPUB metadata so publisher ads cannot leak into the shelf.
    """
    stem = path.stem.strip()
    match = _NAME.match(stem)
    if not match:
        return stem, ""
    title = match.group("title").strip()
    author = match.group("author").strip()
    return title or stem, author
