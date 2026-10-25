"""The terminal client's persistent image cache."""

from __future__ import annotations

import os
from io import BytesIO

from PIL import Image
import pytest


def image_bytes(color: str = "red") -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (8, 8), color).save(buffer, format="PNG")
    return buffer.getvalue()


def test_image_cache_round_trip_and_hashed_path(tmp_path):
    from lector_tui.cache import ImageCache

    cache = ImageCache(tmp_path)
    data = image_bytes()
    assert cache.get("book-1", "OEBPS/cover.jpg") is None
    assert cache.put("book-1", "OEBPS/cover.jpg", data)
    assert cache.get("book-1", "OEBPS/cover.jpg") == data

    files = list(tmp_path.rglob("*.img"))
    assert len(files) == 1
    assert "cover" not in files[0].name
    assert oct(files[0].stat().st_mode)[-3:] == "600"


def test_image_cache_ignores_oversized_entries(tmp_path):
    from lector_tui.cache import ImageCache

    data = image_bytes()
    cache = ImageCache(tmp_path, max_item_bytes=len(data) - 1)
    assert cache.put("book-1", "large.jpg", data) is False
    assert cache.get("book-1", "large.jpg") is None


def test_image_cache_prunes_least_recently_used(tmp_path):
    from lector_tui.cache import ImageCache

    data = image_bytes()
    cache = ImageCache(tmp_path, max_bytes=2 * len(data))
    assert cache.put("book-1", "old.jpg", data)
    old = next(tmp_path.rglob("*.img"))
    os.utime(old, (1, 1))
    assert cache.put("book-1", "new.jpg", data)
    assert cache.put("book-1", "newest.jpg", data)

    assert cache.get("book-1", "old.jpg") is None
    assert cache.get("book-1", "newest.jpg") == data


def test_image_cache_isolates_servers_and_reuses_the_same_namespace(tmp_path):
    from lector_tui.cache import ImageCache

    first = ImageCache(tmp_path, namespace="https://first.example/ebook")
    second = ImageCache(tmp_path, namespace="https://second.example/ebook")
    default = ImageCache(tmp_path)
    red, blue = image_bytes("red"), image_bytes("blue")
    assert first.put("book-1", "cover", red)
    assert second.get("book-1", "cover") is None
    assert default.get("book-1", "cover") is None
    assert second.put("book-1", "cover", blue)
    assert first.get("book-1", "cover") == red
    assert second.get("book-1", "cover") == blue
    assert ImageCache(tmp_path, namespace=first.namespace).get("book-1", "cover") == red


@pytest.mark.parametrize("data", [b"", b"not an image", image_bytes()[:-12]])
def test_image_cache_rejects_invalid_or_truncated_images(tmp_path, data):
    from lector_tui.cache import ImageCache

    cache = ImageCache(tmp_path)
    assert cache.put("book-1", "cover", data) is False
    assert cache.get("book-1", "cover") is None
    assert not list(tmp_path.rglob("*.img"))


def test_image_cache_evicts_corrupted_entry_and_allows_replacement(tmp_path):
    from lector_tui.cache import ImageCache

    cache = ImageCache(tmp_path)
    data = image_bytes()
    assert cache.put("book-1", "cover", data)
    path = next(tmp_path.rglob("*.img"))
    path.write_bytes(b"corrupted")
    assert cache.get("book-1", "cover") is None
    assert not path.exists()
    assert cache.put("book-1", "cover", data)
    assert cache.get("book-1", "cover") == data


def test_image_cache_evicts_oversized_disk_entry(tmp_path):
    from lector_tui.cache import ImageCache

    data = image_bytes()
    cache = ImageCache(tmp_path, max_item_bytes=len(data))
    assert cache.put("book-1", "cover", data)
    path = next(tmp_path.rglob("*.img"))
    path.write_bytes(data + b"x")
    assert cache.get("book-1", "cover") is None
    assert not path.exists()


@pytest.mark.parametrize("option", ["max_item_bytes", "max_bytes"])
def test_negative_cache_budgets_are_rejected(tmp_path, option):
    from lector_tui.cache import ImageCache

    with pytest.raises(ValueError):
        ImageCache(tmp_path, **{option: -2})


def test_disk_reads_are_bounded_even_for_growing_or_tampered_files(tmp_path, monkeypatch):
    from pathlib import Path
    from lector_tui.cache import ImageCache

    data = image_bytes()
    cache = ImageCache(tmp_path, max_item_bytes=len(data))
    assert cache.put("book-1", "cover", data)
    original_open = Path.open
    sizes = []

    class BoundedReader:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, size=-1):
            sizes.append(size)
            assert 0 < size <= len(data) + 1
            return data + b"x"

    def open_path(path, mode="r", *args, **kwargs):
        if mode == "rb":
            return BoundedReader()
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", open_path)
    assert cache.get("book-1", "cover") is None
    assert sizes
    assert not list(tmp_path.rglob("*.img"))


def test_failed_atomic_write_preserves_previous_image_and_cleans_temporary_file(tmp_path, monkeypatch):
    from lector_tui.cache import ImageCache

    cache = ImageCache(tmp_path)
    data = image_bytes()
    assert cache.put("book-1", "cover", data)

    def fail_replace(*args):
        raise OSError("disk full")

    monkeypatch.setattr("lector_tui.cache.os.replace", fail_replace)
    assert not cache.put("book-1", "cover", image_bytes("blue"))
    assert cache.get("book-1", "cover") == data
    assert not list(tmp_path.rglob("*.tmp"))


def test_invalid_disk_images_over_pixel_budget_are_evicted(tmp_path, monkeypatch):
    from lector_tui.cache import ImageCache

    cache = ImageCache(tmp_path)
    data = image_bytes()
    assert cache.put("book-1", "cover", data)
    monkeypatch.setattr("lector_tui.image_data.MAX_IMAGE_PIXELS", 63)
    assert cache.get("book-1", "cover") is None
    assert not list(tmp_path.rglob("*.img"))
    assert not cache.put("book-1", "cover", data)
