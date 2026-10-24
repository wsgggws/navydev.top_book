"""The terminal client.

The tests drive the real Textual application against a real server.
"""

from __future__ import annotations

import asyncio
import socket
import threading
import time

import pytest

from lector.config import load_settings
from lector.web import create_app


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def server(tmp_path):
    """A real HTTP server the terminal can talk to."""
    import uvicorn

    settings = load_settings(tmp_path / "data")
    app = create_app(settings)
    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    instance = uvicorn.Server(config)
    thread = threading.Thread(target=instance.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not instance.started and time.time() < deadline:
        time.sleep(0.05)
    assert instance.started, "the test server did not start"
    yield f"http://127.0.0.1:{port}"
    instance.should_exit = True
    thread.join(timeout=5)


def test_terminal_opens_a_book_and_reads(server, epub2_bytes: bytes):
    """The shelf lists the book and the reader shows its sentences."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "terminal"))
    from lector_tui.app import LectorApp

    import httpx

    httpx.post(
        f"{server}/api/v1/books",
        files={"file": ("book.epub", epub2_bytes, "application/epub+zip")},
    )

    async def scenario():
        app = LectorApp(base_url=server)
        async with app.run_test() as pilot:
            await pilot.pause()
            listing = app.screen.query_one("#library-list")
            assert listing.query("ListItem")

            await pilot.press("enter")
            await pilot.pause()
            assert app.screen.__class__.__name__ == "ReaderScreen"
            chapter = app.screen.query_one("ChapterText")
            assert chapter.chapter is not None
            assert app.screen.sentences
            assert app.screen.cursor is not None
            assert app.screen.cursor["chapter_id"].startswith("c")

    asyncio.run(scenario())


def test_terminal_moves_the_cursor(server, epub2_bytes: bytes):
    """Arrow keys move the one cursor."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "terminal"))
    from lector_tui.app import LectorApp

    import httpx

    httpx.post(
        f"{server}/api/v1/books",
        files={"file": ("book.epub", epub2_bytes, "application/epub+zip")},
    )

    async def scenario():
        app = LectorApp(base_url=server)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            first = app.screen.cursor["sentence_id"]
            await pilot.press("right")
            await pilot.pause()
            assert app.screen.cursor["sentence_id"] != first
            await pilot.press("left")
            await pilot.pause()
            assert app.screen.cursor["sentence_id"] == first

    asyncio.run(scenario())


def test_terminal_pushes_the_progress(server, epub2_bytes: bytes):
    """``s`` sends the position to the server."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "terminal"))
    from lector_tui.app import LectorApp

    import httpx

    upload = httpx.post(
        f"{server}/api/v1/books",
        files={"file": ("book.epub", epub2_bytes, "application/epub+zip")},
    )
    book_id = upload.json()["book"]["book_id"]

    async def scenario():
        app = LectorApp(base_url=server)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("right")
            await pilot.pause()
            await pilot.press("s")
            await pilot.pause()
            progress = httpx.get(f"{server}/api/v1/books/{book_id}/progress").json()
            assert progress["cursor"] is not None
            assert progress["cursor"]["sentence_id"] == app.screen.cursor["sentence_id"]
            assert progress["updated_by"] == "terminal"

    asyncio.run(scenario())
