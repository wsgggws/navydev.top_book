"""Terminal theme detection."""

from __future__ import annotations

from lector_tui import theme


def test_explicit_theme_is_kept():
    assert theme.resolve_theme("dracula") == "dracula"


def test_auto_uses_colorfgbg_without_probing(monkeypatch):
    monkeypatch.delenv("LECTOR_THEME_BACKGROUND", raising=False)
    monkeypatch.setenv("COLORFGBG", "15;0")
    assert theme.resolve_theme("auto", probe=False) == "ansi-dark"

    monkeypatch.setenv("COLORFGBG", "0;15")
    assert theme.resolve_theme("auto", probe=False) == "ansi-light"


def test_explicit_background_override_wins(monkeypatch):
    monkeypatch.setenv("LECTOR_THEME_BACKGROUND", "light")
    assert theme.terminal_background_tone(probe=False) == "light"


def test_osc11_rgb_is_turned_into_a_tone(monkeypatch):
    monkeypatch.delenv("LECTOR_THEME_BACKGROUND", raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")
    monkeypatch.setattr(theme, "_query_osc11_background", lambda timeout=0.12: (255, 255, 255))
    assert theme.resolve_theme("auto", probe=True) == "ansi-light"

    monkeypatch.setattr(theme, "_query_osc11_background", lambda timeout=0.12: (0, 0, 0))
    assert theme.resolve_theme("auto", probe=True) == "ansi-dark"


def test_terminal_rgb_snapshot_is_strict_and_scales_channels():
    result = theme.parse_terminal_colors(
        b"\x1b]10;rgb:3434/2f2f/2323\x1b\\\x1b]11;rgb:d9/bd/7a\x07\x1b]4;4;rgb:2424/4b4b/6666\x1b\\"
    )
    assert result == {"foreground": "#342f23", "background": "#d9bd7a", "accent": "#244b66"}
    assert theme.parse_terminal_colors(b"\x1b]11;rgb:wrong\x07") == {}


def test_auto_theme_uses_readable_terminal_rgb_instead_of_ansi_defaults():
    from lector_tui.app import LectorApp

    app = LectorApp(
        theme="ansi-light",
        terminal_colors={
            "foreground": "#342f23",
            "background": "#d9bd7a",
            "accent": "#244b66",
        },
    )
    assert app.current_theme.foreground == "#342f23"
    assert app.current_theme.background == "#d9bd7a"
    assert app.current_theme.ansi is False
    app.audio.cleanup()


def test_shelf_selection_keeps_text_readable_in_light_and_dark_palettes(monkeypatch):
    import asyncio
    from lector_tui.api import ApiClient
    from lector_tui.app import LectorApp
    from textual.widgets import Static
    from lector_tui.screens.library import BookItem

    monkeypatch.setattr(
        ApiClient,
        "list_books",
        lambda self: [
            {"book_id": "b_test", "title": "Readable selection", "author": "Author"},
        ],
    )

    def luminance(color):
        channels = [value / 255 for value in (color.r, color.g, color.b)]
        linear = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in channels]
        return sum(value * weight for value, weight in zip(linear, (0.2126, 0.7152, 0.0722)))

    async def scenario():
        for palette in [
            {"foreground": "#342f23", "background": "#d9bd7a", "accent": "#244b66"},
            {"foreground": "#f8f8f2", "background": "#282a36", "accent": "#bd93f9"},
        ]:
            app = LectorApp(theme="ansi-light", terminal_colors=palette)
            async with app.run_test() as pilot:
                await pilot.pause(0.1)
                row = app.screen.query_one(BookItem)
                title = row.query_one(".book-title", Static)
                light = luminance(title.styles.color)
                dark = luminance(row.background_colors[1])
                contrast = (max(light, dark) + 0.05) / (min(light, dark) + 0.05)
                assert contrast >= 4.5, contrast
            app.audio.cleanup()

    asyncio.run(scenario())
