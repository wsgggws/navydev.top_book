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
