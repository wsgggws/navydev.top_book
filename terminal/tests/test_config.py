"""The terminal client's own settings.

These tests need no server: the terminal project stands on its own.
"""

from __future__ import annotations

import json


def test_config_is_saved_and_read_back(tmp_path, monkeypatch):
    """The address and the token survive a restart."""
    from lector_tui.config import ClientConfig

    monkeypatch.delenv("LECTOR_URL", raising=False)
    monkeypatch.delenv("LECTOR_TOKEN", raising=False)
    path = tmp_path / "reader.json"

    config = ClientConfig(
        url="https://reader.example.com",
        token="secret",
        theme="dracula",
        path=path,
    )
    config.save()
    assert path.exists()
    assert json.loads(path.read_text())["url"] == "https://reader.example.com"

    again = ClientConfig.load(path=path)
    assert again.url == "https://reader.example.com"
    assert again.token == "secret"
    assert again.theme == "dracula"


def test_environment_wins_over_the_file(tmp_path, monkeypatch):
    """LECTOR_URL and LECTOR_TOKEN override what was saved."""
    from lector_tui.config import ClientConfig

    path = tmp_path / "reader.json"
    path.write_text(json.dumps({"url": "http://old", "token": "old", "theme": "paper"}))
    monkeypatch.setenv("LECTOR_URL", "http://new")
    monkeypatch.setenv("LECTOR_TOKEN", "new")
    monkeypatch.setenv("LECTOR_THEME", "catppuccin-mocha")

    config = ClientConfig.load(path=path)
    assert config.url == "http://new"
    assert config.token == "new"
    assert config.theme == "catppuccin-mocha"
    assert json.loads(path.read_text())["url"] == "http://old"


def test_default_endpoint_is_the_public_ebook(monkeypatch, tmp_path):
    from lector_tui.config import ClientConfig

    monkeypatch.delenv("LECTOR_URL", raising=False)
    monkeypatch.delenv("LECTOR_TOKEN", raising=False)
    monkeypatch.delenv("LECTOR_THEME", raising=False)
    config = ClientConfig.load(path=tmp_path / "reader.json")
    assert config.url == "https://navydev.top/ebook"
    assert config.theme == "auto"


def test_token_file_is_not_world_readable(tmp_path, monkeypatch):
    """The token file is private to the user."""
    from lector_tui.config import ClientConfig

    monkeypatch.delenv("LECTOR_URL", raising=False)
    monkeypatch.delenv("LECTOR_TOKEN", raising=False)
    path = tmp_path / "reader.json"
    ClientConfig(url="http://x", token="secret", path=path).save()
    assert oct(path.stat().st_mode)[-3:] == "600"
