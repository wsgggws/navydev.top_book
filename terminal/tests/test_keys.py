"""Read-only navigation and playback bindings."""

from __future__ import annotations


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
