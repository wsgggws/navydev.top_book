"""The terminal client's own settings.

The reader talks to a server that may live on this machine or on the internet,
so the address and the access token belong to the client, not to the code.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

#: Where the settings live.
CONFIG_DIR = Path(
    os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")
) / "lector"
CONFIG_FILE = CONFIG_DIR / "reader.json"
PROGRESS_FILE = CONFIG_DIR / "progress.json"
DEFAULT_URL = "https://navydev.top/ebook"


@dataclass
class ClientConfig:
    """Where the server is and how to talk to it."""

    url: str = DEFAULT_URL
    token: str = ""
    theme: str = "auto"
    path: Path = CONFIG_FILE

    @classmethod
    def load(cls, path: Path | None = None) -> "ClientConfig":
        """Read the settings, falling back to the environment.

        The environment wins over the file: it is the more explicit of the two.
        """
        url = os.environ.get("LECTOR_URL", "").strip()
        token = os.environ.get("LECTOR_TOKEN", "").strip()
        theme = os.environ.get("LECTOR_THEME", "").strip()
        config = cls(
            url=url or cls.url,
            token=token,
            theme=theme or cls.theme,
            path=path or CONFIG_FILE,
        )
        if config.path.exists():
            try:
                payload = json.loads(config.path.read_text("utf-8"))
            except (OSError, ValueError):
                return config
            # 环境变量优先于文件。
            if not url:
                config.url = str(payload.get("url") or config.url).rstrip("/")
            if not token:
                config.token = str(payload.get("token") or "")
            if not theme:
                config.theme = str(payload.get("theme") or config.theme)
        return config

    def save(self) -> None:
        """Write the settings to disk."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(
                {"url": self.url, "token": self.token, "theme": self.theme},
                ensure_ascii=False,
                indent=2,
            ),
            "utf-8",
        )
        try:
            self.path.chmod(0o600)
        except OSError:
            pass

    def describe(self) -> str:
        """A one line description for the shelf."""
        if self.token:
            return f"{self.url}（已带令牌）"
        return self.url


@dataclass
class ProgressStore:
    """终端自己的阅读位置。

    网页与终端是两套独立的阅读器：这里记的是"这台机器上的终端读到哪"，
    不和服务端、也不和网页共享。
    """

    path: Path = PROGRESS_FILE
    data: dict = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path | None = None) -> "ProgressStore":
        override = os.environ.get("LECTOR_PROGRESS_FILE")
        store = cls(path=path or (Path(override) if override else PROGRESS_FILE))
        if store.path.exists():
            try:
                payload = json.loads(store.path.read_text("utf-8"))
                if isinstance(payload, dict):
                    store.data = payload
            except (OSError, ValueError):
                pass
        return store

    def get(self, book_id: str) -> dict | None:
        """这本书上次读到哪。"""
        entry = self.data.get(book_id)
        return dict(entry) if isinstance(entry, dict) else None

    def set(
        self,
        book_id: str,
        chapter_id: str,
        sentence_id: str,
        word_index: int | None = None,
        percent: float | None = None,
    ) -> None:
        """记下位置；百分比由调用方算了才传。"""
        previous = self.data.get(book_id) or {}
        if percent is None:
            same = (
                previous.get("chapter_id") == chapter_id
                and previous.get("sentence_id") == sentence_id
            )
            percent = previous.get("percent", 0.0) if same else 0.0
        self.data[book_id] = {
            "chapter_id": chapter_id,
            "sentence_id": sentence_id,
            "word_index": word_index,
            "percent": percent,
        }
        self.save()

    def percent(self, book_id: str) -> float:
        entry = self.data.get(book_id) or {}
        try:
            return float(entry.get("percent", 0.0))
        except (TypeError, ValueError):
            return 0.0

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), "utf-8")
        tmp.replace(self.path)
        try:
            self.path.chmod(0o600)
        except OSError:
            pass
