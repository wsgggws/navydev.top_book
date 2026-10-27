"""Startup remains responsive while the server is slow or unavailable."""

import asyncio
import threading

from textual.widgets import Input


def test_slow_shelf_request_does_not_block_first_paint_or_keys(tmp_path, monkeypatch):
    from lector_tui.api import ApiClient
    from lector_tui.app import LectorApp

    monkeypatch.setattr("lector_tui.cache.CACHE_DIR", tmp_path)
    started, release, finished = threading.Event(), threading.Event(), threading.Event()

    def list_books(self):
        started.set()
        release.wait(2)
        finished.set()
        return []

    monkeypatch.setattr(ApiClient, "list_books", list_books)

    async def scenario():
        app = LectorApp(base_url="https://slow.test/ebook", theme="night")
        try:
            async with app.run_test() as pilot:
                await pilot.pause(.05)
                assert started.is_set()
                assert not finished.is_set(), "the first screen waited for the network instead of painting"
                await pilot.press("c")
                assert app.screen.query_one("#connect-url", Input).has_focus
                release.set()
                await pilot.pause(.1)
        finally:
            release.set()

    asyncio.run(scenario())


def test_cached_shelf_survives_offline_and_preserves_cover_widgets(tmp_path, monkeypatch):
    from textual.widgets import Static
    from lector_tui.api import ApiClient
    from lector_tui.app import LectorApp
    from lector_tui.image_widget import TerminalImage
    from lector_tui.images import placeholder_cover
    from lector_tui.screens.library import BookItem
    from lector_tui.shelf_cache import ShelfCache

    monkeypatch.setattr("lector_tui.cache.CACHE_DIR", tmp_path)
    books = [{"book_id": "cached", "title": "Cached book", "author": "Author"}]
    ShelfCache("https://offline.test/ebook").put(books)
    started, release = threading.Event(), threading.Event()

    def list_books(self):
        started.set()
        release.wait(3)
        raise OSError("offline")

    monkeypatch.setattr(ApiClient, "list_books", list_books)

    async def scenario():
        app = LectorApp(base_url="https://offline.test/ebook", token="", theme="night")
        try:
            async with app.run_test() as pilot:
                await pilot.pause(.05)
                assert started.is_set()
                row = app.screen.query_one(BookItem)
                cover = row.query_one(TerminalImage)
                row.set_cover(placeholder_cover())
                image = cover.image
                assert image is not None
                app.screen.refresh_books()
                await pilot.pause(.05)
                app.screen._render_books(books)
                await pilot.pause()
                assert app.screen.query_one(BookItem) is row
                assert cover.image is image, "identical shelf refresh must retain its image"
                row.set_percent(42)
                assert "42%" in row.query_one(".book-meta", Static).render().plain
                release.set()
                await pilot.pause(.2)
                assert app.screen.query_one(BookItem) is row
                assert "刷新失败" in app.screen.query_one("#shelf-server", Static).render().plain
                # A previous connection's delayed callback cannot replace this shelf.
                app.screen._books_loaded(app.screen._refresh_generation - 1, app.screen._snapshot_key, [])
                app.screen._books_failed(app.screen._refresh_generation, ("https://other.test", ""), "stale")
                assert app.screen.query_one(BookItem) is row
        finally:
            release.set()

    asyncio.run(scenario())


def test_shelf_cache_is_private_bounded_and_separates_connections(tmp_path):
    import json
    from lector_tui.shelf_cache import MAX_SHELF_BYTES, ShelfCache

    books = [{"book_id": "b_1", "title": "中文书", "author": None}]
    cache = ShelfCache("https://example.test/ebook", "private-token", root=tmp_path)
    assert cache.get() is None
    cache.put(books)
    assert cache.get() == books
    assert cache.path.stat().st_mode & 0o777 == 0o600
    assert "private-token" not in cache.path.name
    assert ShelfCache("https://example.test/ebook/", "private-token", root=tmp_path).get() == books
    assert ShelfCache("https://example.test/ebook", "other-token", root=tmp_path).get() is None
    assert ShelfCache("https://other.test/ebook", "private-token", root=tmp_path).get() is None
    for data in [b"invalid", b"x" * (MAX_SHELF_BYTES + 1),
                 json.dumps({"version": 2, "books": books}).encode(),
                 json.dumps({"version": 1, "books": [{"book_id": "../bad", "title": "Bad"}]}).encode()]:
        cache.path.write_bytes(data)
        assert cache.get() is None
    cache.put([{"book_id": "b_1", "title": "x" * 4097}])
    assert cache.get() is None
