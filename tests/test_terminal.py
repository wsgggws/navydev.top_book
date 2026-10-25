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


def test_terminal_check_mode_connects_without_a_token(
    server, epub2_bytes: bytes, capsys
):
    """The packaged binary can verify HTTPS and the API without opening the TUI."""
    import httpx

    from lector_tui.app import main

    httpx.post(
        f"{server}/api/v1/books",
        files={"file": ("book.epub", epub2_bytes, "application/epub+zip")},
    )
    main(["--check", "--url", server, "--token", ""])
    output = capsys.readouterr().out
    assert "OK" in output
    assert "1 books" in output


def test_terminal_moves_the_cursor(server, epub2_bytes: bytes):
    """Arrow keys move the one cursor."""
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


def test_vim_keys_move_the_cursor(server, epub2_bytes: bytes):
    """``h`` and ``l`` move the cursor the way vim moves the cursor."""
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
            await pilot.press("l")
            await pilot.pause()
            second = app.screen.cursor["sentence_id"]
            assert second != first
            await pilot.press("h")
            await pilot.pause()
            assert app.screen.cursor["sentence_id"] == first

    asyncio.run(scenario())


def test_fullscreen_toggles_the_text_pane(server, epub2_bytes: bytes):
    """``f`` expands the text to the whole screen and back."""
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
            assert not app.screen.has_class("fullscreen")
            await pilot.press("f")
            await pilot.pause()
            assert app.screen.has_class("fullscreen")
            await pilot.press("f")
            await pilot.pause()
            assert not app.screen.has_class("fullscreen")

    asyncio.run(scenario())


def test_search_finds_and_jumps(server, epub2_bytes: bytes):
    """``/`` searches the book and the hits land in the directory pane."""
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
            await pilot.press("/")
            await pilot.pause()
            assert app.screen.query_one("#search-input").display
            app.screen.query_one("#search-input").value = "玫瑰"
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert app.screen._hits
            target = app.screen._hits[0]["sentence_id"]
            await pilot.press("n")
            await pilot.pause()
            assert app.screen.cursor["sentence_id"] in {
                hit["sentence_id"] for hit in app.screen._hits
            }
            assert target

    asyncio.run(scenario())


def test_the_terminal_does_not_change_the_shelf(server, epub2_bytes: bytes):
    """终端端只读：书架上没有上传与删除。"""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "terminal"))
    from lector_tui.app import LectorApp

    async def scenario():
        app = LectorApp(base_url=server)
        async with app.run_test() as pilot:
            await pilot.pause()
            from lector_tui.screens.library import LibraryScreen

            keys = {binding.key for binding in LibraryScreen.BINDINGS}
            assert "u" not in keys
            assert "d" not in keys
            assert "enter" in keys
            assert "c" in keys
            # 界面上也没有上传输入框。
            assert not app.screen.query("#upload-input")

    asyncio.run(scenario())


def test_the_shelf_moves_with_jk(server, epub2_bytes: bytes):
    """书架上 j/k 能上下移动，l 进入。"""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "terminal"))
    from lector_tui.app import LectorApp

    import httpx

    import sys as _sys
    from pathlib import Path as _Path

    _sys.path.insert(0, str(_Path(__file__).resolve().parent))
    from factories import build_epub2

    # 两本不同的书，书架上才有得上下移动。
    for title in ("甲书", "乙书"):
        httpx.post(
            f"{server}/api/v1/books",
            files={
                "file": (
                    f"{title}.epub",
                    build_epub2(title=title),
                    "application/epub+zip",
                )
            },
        )

    async def scenario():
        app = LectorApp(base_url=server)
        async with app.run_test() as pilot:
            await pilot.pause()
            listing = app.screen.query_one("#library-list")
            assert listing.index == 0
            await pilot.press("j")
            await pilot.pause()
            assert listing.index == 1
            await pilot.press("k")
            await pilot.pause()
            assert listing.index == 0
            # l 进入书里
            await pilot.press("l")
            await pilot.pause()
            assert app.screen.__class__.__name__ == "ReaderScreen"

    asyncio.run(scenario())


def test_terminal_remembers_the_position_locally(server, epub2_bytes: bytes, tmp_path, monkeypatch):
    """终端把位置记在自己的文件里，重启还接着上次那一处。"""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "terminal"))
    from lector_tui.app import LectorApp

    import httpx

    progress_file = tmp_path / "progress.json"
    monkeypatch.setenv("LECTOR_PROGRESS_FILE", str(progress_file))
    httpx.post(
        f"{server}/api/v1/books",
        files={"file": ("book.epub", epub2_bytes, "application/epub+zip")},
    )

    async def first_run() -> str:
        app = LectorApp(base_url=server)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("l")
            await pilot.press("l")
            await pilot.pause()
            return app.screen.cursor["sentence_id"]

    saved = asyncio.run(first_run())
    assert progress_file.exists()

    async def second_run() -> str:
        app = LectorApp(base_url=server)
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            return app.screen.cursor["sentence_id"]

    assert asyncio.run(second_run()) == saved


def test_terminal_does_not_touch_the_servers_progress(server, epub2_bytes: bytes, tmp_path, monkeypatch):
    """终端只读：它不动服务端的进度，也不会把网页顶走。"""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "terminal"))
    from lector_tui.app import LectorApp

    import httpx

    monkeypatch.setenv("LECTOR_PROGRESS_FILE", str(tmp_path / "progress.json"))
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
            for _ in range(3):
                await pilot.press("l")
                await pilot.pause()
            await pilot.pause(1.5)

    asyncio.run(scenario())
    progress = httpx.get(f"{server}/api/v1/books/{book_id}/progress").json()
    assert progress["cursor"] is None
