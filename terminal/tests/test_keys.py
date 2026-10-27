"""Read-only navigation and playback bindings."""

from __future__ import annotations

import asyncio
import subprocess
import sys

import pytest


def test_vim_navigation_and_play_keys_are_registered():
    from lector_tui.screens.library import LibraryScreen
    from lector_tui.screens.reader import ListenScreen, ReaderScreen
    from lector_tui.widgets import VimListView

    list_keys = {binding.key for binding in VimListView.BINDINGS}
    assert {"j", "k", "l"} <= list_keys

    library_keys = {binding.key for binding in LibraryScreen.BINDINGS}
    assert {"space", "g", "G"} <= library_keys

    reader_keys = {binding.key for binding in ReaderScreen.BINDINGS}
    assert {"space", "p"} <= reader_keys

    listen_keys = {binding.key for binding in ListenScreen.BINDINGS}
    assert {"space", "p", "r", "plus", "minus", "0"} <= listen_keys


def test_builtin_theme_names_are_accepted():
    from lector_tui.app import LectorApp

    app = LectorApp(theme="catppuccin-mocha", theme_preference="catppuccin-mocha")
    assert app.theme == "catppuccin-mocha"
    assert app.theme_preference == "catppuccin-mocha"
    app.audio.cleanup()


def test_reader_highlight_avoids_background_colours_and_keeps_a_wider_page():
    from lector_tui.app import LectorApp

    css = LectorApp.CSS
    assert "text-style: reverse bold" in css
    assert "text-style: bold underline" in css
    assert "width: 92%;" in css
    assert "max-width: 96;" in css
    assert "background: $accent 35%" not in css
    assert "background: $accent 55%" not in css


@pytest.mark.parametrize("screen_name", ["ReaderScreen", "ListenScreen"])
def test_raw_extended_focus_keys_and_existing_pane_keys(monkeypatch, tmp_path, screen_name):
    """Feed real protocol bytes through Textual, then dispatch the parsed events."""
    from textual._xterm_parser import XTermParser
    from lector_tui.api import ApiClient
    from lector_tui.app import LectorApp
    from lector_tui.screens import reader

    monkeypatch.setenv("LECTOR_PROGRESS_FILE", str(tmp_path / "progress.json"))
    monkeypatch.setattr(ApiClient, "list_books", lambda self: [])
    monkeypatch.setattr(reader.BaseReaderScreen, "load_book", lambda self: None)
    monkeypatch.setattr(reader.ListenScreen, "start_playback", lambda self: None)

    async def scenario():
        app = LectorApp(theme="night")
        async with app.run_test() as pilot:
            screen = getattr(reader, screen_name)("keys-book")
            await app.push_screen(screen)
            await pilot.pause()

            async def send(sequence):
                events = list(XTermParser().feed(sequence))
                assert len(events) == 1
                app.post_message(events[0])
                await pilot.pause()

            for left, right in [(104, 108), (72, 76)]:
                await send(f"\x1b[{left};6u")
                assert app.focused.id == "toc-pane"
                await send(f"\x1b[{right};6u")
                assert app.focused.id == "text-pane"
            await pilot.press("tab")
            assert app.focused.id == "toc-pane"
            await pilot.press("ctrl+w")
            assert app.focused.id == "text-pane"
            await pilot.press("t")
            assert app.focused.id == "toc-pane"
            redrawn = []
            monkeypatch.setattr(app, "action_refresh_images", lambda: redrawn.append(True))
            await pilot.press("ctrl+l")
            assert redrawn == [True]
            assert app.focused.id == "toc-pane"
            await pilot.press("slash")
            assert app.focused.id == "search-input"
            field = app.focused
            field.value = "abc"
            field.cursor_position = 3
            await send("\x08")
            assert field.value == "ab"
            assert app.focused is field
            await send("\x1b[108;6u")
            assert app.focused.id == "text-pane"

    asyncio.run(scenario())


def test_legacy_and_modify_other_keys_cannot_supply_shift_focus_bindings():
    from textual._xterm_parser import XTermParser

    # Legacy Ctrl+Shift+L/H are the very same bytes as Ctrl+L / Backspace.
    for sequence, key in [("\x0c", "ctrl+l"), ("\x08", "backspace"),
                          ("\x1b[27;6;108~", "ctrl+l"), ("\x1b[27;6;104~", "ctrl+h")]:
        events = list(XTermParser().feed(sequence))
        assert [event.key for event in events] == [key]


def test_q_quits_from_the_bookshelf(monkeypatch):
    """The shelf's advertised quit key must actually end the application."""
    from lector_tui.api import ApiClient
    from lector_tui.app import LectorApp
    from lector_tui.screens.library import LibraryScreen

    monkeypatch.setattr(ApiClient, "list_books", lambda self: [])
    app = LectorApp(
        base_url="http://127.0.0.1:1",
        theme="night",
        theme_preference="night",
    )

    async def scenario() -> None:
        async with app.run_test() as pilot:
            await pilot.pause()
            assert isinstance(app.screen, LibraryScreen)
            await pilot.press("q")
            assert app.is_running is False

    asyncio.run(scenario())


def test_app_import_does_not_probe_terminal_graphics():
    """--version and --check must not emit image-protocol escape sequences."""
    code = "import sys\nimport lector_tui.app\nraise SystemExit('textual_image' in sys.modules)\n"
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""


def test_reader_uses_spine_order_even_when_toc_is_nested_or_incomplete():
    from types import SimpleNamespace
    from lector_tui.screens.reader import BaseReaderScreen

    seen = []
    api = SimpleNamespace(
        base_url="https://example.test/ebook",
        get_book=lambda book_id: {"book": {"chapter_count": 12}},
        get_toc=lambda book_id: [{"chapter_id": "c10", "children": [{"chapter_id": "c2"}]}],
    )
    reader = SimpleNamespace(
        book_id="b_test",
        app=SimpleNamespace(api=api),
        _image_store=SimpleNamespace(namespace=""),
        progress=SimpleNamespace(get=lambda book_id: None),
        render_toc=lambda: None,
        first_readable_chapter=lambda: "c0",
        load_chapter=lambda *args: seen.append(args),
    )
    BaseReaderScreen.load_book(reader)
    assert reader.chapter_ids == [f"c{index}" for index in range(12)]
    assert seen == [("c0", None)]


def test_listening_rate_is_local_to_each_book_and_survives_restart(tmp_path, monkeypatch):
    from lector_tui.api import ApiClient
    from lector_tui.app import LectorApp
    from lector_tui.screens.reader import ListenScreen

    monkeypatch.setenv('LECTOR_PROGRESS_FILE', str(tmp_path / 'progress.json'))
    monkeypatch.setattr(ApiClient, 'list_books', lambda self: [])
    monkeypatch.setattr(ListenScreen, 'load_book', lambda self: setattr(self, 'book', {'language': 'zh-CN'}))
    monkeypatch.setattr(ApiClient, 'voices', lambda self: {'voices': [
        {'voice_id': 'zh-male', 'locale': 'zh-CN', 'gender': 'male'},
        {'voice_id': 'zh-female', 'locale': 'zh-CN', 'gender': 'female'},
    ]})
    monkeypatch.setattr(ListenScreen, 'start_playback', lambda self: None)

    async def scenario():
        app = LectorApp(theme='night')
        async with app.run_test() as pilot:
            a = ListenScreen('a')
            await app.push_screen(a)
            await pilot.press('plus')
            assert app.audio.rate == 1.25
            await pilot.press('v')
            assert a.voice_id == 'zh-female'
            await app.pop_screen()
            await app.push_screen(ListenScreen('b'))
            assert app.audio.rate == 1.0, 'new books start at the default rate'
            assert app.screen.voice_gender == 'male'
            assert app.screen.voice_id == ''
            await pilot.press('minus')
            await app.pop_screen()
            await app.push_screen(ListenScreen('a'))
            assert app.audio.rate == 1.25
            assert app.screen.voice_gender == 'female'
            assert app.screen.voice_id == 'zh-female'
        app = LectorApp(theme='night')
        async with app.run_test():
            await app.push_screen(ListenScreen('b'))
            assert app.audio.rate == 0.75, 'book settings survive client restart'

    asyncio.run(scenario())
