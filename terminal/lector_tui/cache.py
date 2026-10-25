"""Persistent cache for downloaded images.

Terminal image protocols are expensive to re-download, especially when moving
back and forth in the shelf.  The cache is local to this machine and contains
only public EPUB cover/media bytes; it is never uploaded anywhere.
"""

from __future__ import annotations

import hashlib
import os
import sys
import time
from pathlib import Path


def default_cache_dir() -> Path:
    """The platform-appropriate cache directory for the terminal client."""
    override = os.environ.get("LECTOR_CACHE_DIR")
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    else:
        base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return base / "lector"


CACHE_DIR = default_cache_dir()


class ImageCache:
    """A small content-addressed cache for EPUB images."""

    def __init__(
        self,
        root: Path | None = None,
        *,
        max_bytes: int = 512 * 1024 * 1024,
        max_item_bytes: int = 20 * 1024 * 1024,
    ) -> None:
        self.root = root or (CACHE_DIR / "images")
        self.max_bytes = max_bytes
        self.max_item_bytes = max_item_bytes

    def _path(self, book_id: str, name: str) -> Path:
        digest = hashlib.sha256(f"{book_id}\0{name}".encode("utf-8")).hexdigest()
        return self.root / digest[:2] / f"{digest}.img"

    def get(self, book_id: str, name: str) -> bytes | None:
        """Return cached bytes and mark the entry as recently used."""
        path = self._path(book_id, name)
        try:
            data = path.read_bytes()
            os.utime(path, None)
            return data
        except OSError:
            return None

    def put(self, book_id: str, name: str, data: bytes) -> bool:
        """Store bytes atomically; oversized or unwritable entries are ignored."""
        if not data or len(data) > self.max_item_bytes:
            return False
        path = self._path(book_id, name)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(f".{os.getpid()}.{time.monotonic_ns()}.tmp")
            temporary.write_bytes(data)
            os.replace(temporary, path)
            try:
                path.chmod(0o600)
            except OSError:
                pass
        except OSError:
            try:
                temporary.unlink(missing_ok=True)
            except (OSError, UnboundLocalError):
                pass
            return False
        self.prune()
        return True

    def prune(self) -> None:
        """Drop least-recently-used entries when the cache grows too large."""
        files: list[tuple[float, Path, int]] = []
        try:
            for path in self.root.rglob("*.img"):
                try:
                    stat = path.stat()
                except OSError:
                    continue
                files.append((stat.st_mtime, path, stat.st_size))
        except OSError:
            return
        total = sum(size for _, _, size in files)
        if total <= self.max_bytes:
            return
        target = int(self.max_bytes * 0.9)
        for _, path, size in sorted(files, key=lambda item: item[0]):
            try:
                path.unlink()
                total -= size
            except OSError:
                continue
            if total <= target:
                break
