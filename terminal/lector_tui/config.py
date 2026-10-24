"""The terminal client's own settings.

The reader talks to a server that may live on this machine or on the internet,
so the address and the access token belong to the client, not to the code.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

#: Where the settings live.
CONFIG_DIR = Path(
    os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")
) / "lector"
CONFIG_FILE = CONFIG_DIR / "reader.json"


@dataclass
class ClientConfig:
    """Where the server is and how to talk to it."""

    url: str = "http://127.0.0.1:8000"
    token: str = ""
    path: Path = CONFIG_FILE

    @classmethod
    def load(cls, path: Path | None = None) -> "ClientConfig":
        """Read the settings, falling back to the environment.

        The environment wins over the file: it is the more explicit of the two.
        """
        url = os.environ.get("LECTOR_URL", "").strip()
        token = os.environ.get("LECTOR_TOKEN", "").strip()
        config = cls(url=url or cls.url, token=token, path=path or CONFIG_FILE)
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
        return config

    def save(self) -> None:
        """Write the settings to disk."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({"url": self.url, "token": self.token}, ensure_ascii=False, indent=2),
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
