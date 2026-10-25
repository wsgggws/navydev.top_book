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

from lector_tui.image_data import MAX_IMAGE_BYTES, is_valid_image


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
        namespace: str = "",
        max_bytes: int = 512 * 1024 * 1024,
        max_item_bytes: int = MAX_IMAGE_BYTES,
    ) -> None:
        if max_bytes < 0 or max_item_bytes < 0:
            raise ValueError("Image cache byte limits must be non-negative")
        self.root = root or (CACHE_DIR / "images")
        self.namespace = namespace
        self.max_bytes = max_bytes
        self.max_item_bytes = min(max_item_bytes, MAX_IMAGE_BYTES)

    def _path(self, book_id: str, name: str) -> Path:
        # Hash the namespace separately so separators in a URL or book ID cannot
        # make two distinct keys alias. Empty namespaces retain the legacy path.
        key = f"{book_id}\0{name}".encode("utf-8")
        if self.namespace:
            key = hashlib.sha256(self.namespace.encode("utf-8")).digest() + b"\0" + key
        digest = hashlib.sha256(key).hexdigest()
        return self.root / digest[:2] / f"{digest}.img"

    def get(self, book_id: str, name: str) -> bytes | None:
        """Return cached bytes and mark the entry as recently used."""
        path = self._path(book_id, name)
        try:
            with path.open("rb") as handle:
                data = handle.read(self.max_item_bytes + 1)
            if len(data) > self.max_item_bytes or not is_valid_image(data):
                path.unlink(missing_ok=True)
                return None
            os.utime(path, None)
            return data
        except OSError:
            return None

    def put(self, book_id: str, name: str, data: bytes) -> bool:
        """Store bytes atomically; oversized or unwritable entries are ignored."""
        if len(data) > self.max_item_bytes or not is_valid_image(data):
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
