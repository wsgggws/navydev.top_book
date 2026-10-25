"""The terminal client's persistent image cache."""

from __future__ import annotations

import os


def test_image_cache_round_trip_and_hashed_path(tmp_path):
    from lector_tui.cache import ImageCache

    cache = ImageCache(tmp_path)
    assert cache.get("book-1", "OEBPS/cover.jpg") is None
    assert cache.put("book-1", "OEBPS/cover.jpg", b"image bytes")
    assert cache.get("book-1", "OEBPS/cover.jpg") == b"image bytes"

    files = list(tmp_path.rglob("*.img"))
    assert len(files) == 1
    assert "cover" not in files[0].name
    assert oct(files[0].stat().st_mode)[-3:] == "600"


def test_image_cache_ignores_oversized_entries(tmp_path):
    from lector_tui.cache import ImageCache

    cache = ImageCache(tmp_path, max_item_bytes=4)
    assert cache.put("book-1", "large.jpg", b"12345") is False
    assert cache.get("book-1", "large.jpg") is None


def test_image_cache_prunes_least_recently_used(tmp_path):
    from lector_tui.cache import ImageCache

    cache = ImageCache(tmp_path, max_bytes=10)
    assert cache.put("book-1", "old.jpg", b"12345")
    old = next(tmp_path.rglob("*.img"))
    os.utime(old, (1, 1))
    assert cache.put("book-1", "new.jpg", b"67890")
    assert cache.put("book-1", "newest.jpg", b"abcde")

    assert cache.get("book-1", "old.jpg") is None
    assert cache.get("book-1", "newest.jpg") == b"abcde"
