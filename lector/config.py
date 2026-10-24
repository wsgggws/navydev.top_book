"""Runtime configuration.

Every writable path derives from ``data_dir`` so a deployment relocates by
setting ``LECTOR_DATA_DIR`` alone.  Environment variables are read once at
import time through :func:`load_settings` so tests can override them.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

APP_VERSION = "1.0.0"

#: Bump whenever the parser changes ID or block/sentence structure.
PARSER_VERSION = 1

#: Contract: uploads above this size are rejected with 413.
MAX_UPLOAD_BYTES = 50 * 1024 * 1024

#: Contract: refuse archives whose expanded size dwarfs their compressed size.
MAX_EXPANSION_RATIO = 200

#: Contract: a single sentence synthesis may not exceed this many seconds.
TTS_SYNTH_TIMEOUT = 8.0

DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"

#: The voices the interface offers.  The engine knows three hundred of them;
#: a reader wants a handful of familiar ones in their own language.
FEATURED_VOICES = (
    "zh-CN-XiaoxiaoNeural",
    "zh-CN-XiaoyiNeural",
    "zh-CN-YunxiNeural",
    "zh-CN-YunjianNeural",
    "en-US-AriaNeural",
    "en-US-GuyNeural",
    "en-US-JennyNeural",
    "en-US-EricNeural",
    "en-GB-SoniaNeural",
    "en-GB-RyanNeural",
)

REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    """Immutable snapshot of the server configuration."""

    data_dir: Path
    db_path: Path
    books_dir: Path
    audio_dir: Path
    token: str
    host: str
    port: int
    tts_engine: str
    default_voice: str
    max_upload_bytes: int

    @property
    def web_dir(self) -> Path:
        """Directory holding the browser application."""
        return REPO_ROOT / "web"


def _env_int(name: str, fallback: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return fallback
    try:
        return int(raw)
    except ValueError:
        return fallback


def load_settings(data_dir: Path | str | None = None) -> Settings:
    """Build a :class:`Settings` from the environment.

    ``data_dir`` overrides ``LECTOR_DATA_DIR``; it exists so tests can point
    the whole server at a temporary directory.
    """
    root = Path(data_dir or os.environ.get("LECTOR_DATA_DIR") or (REPO_ROOT / "data")).resolve()
    token = os.environ.get("LECTOR_TOKEN", "").strip()
    return Settings(
        data_dir=root,
        db_path=root / "lector.db",
        books_dir=root / "books",
        audio_dir=root / "audio",
        token=token,
        # Without a token the server must not be reachable from the network.
        host=os.environ.get("LECTOR_HOST", "127.0.0.1" if not token else "0.0.0.0"),
        port=_env_int("LECTOR_PORT", 8000),
        tts_engine=os.environ.get("LECTOR_TTS_ENGINE", "edge").strip().lower() or "edge",
        default_voice=os.environ.get("LECTOR_VOICE", DEFAULT_VOICE).strip() or DEFAULT_VOICE,
        max_upload_bytes=_env_int("LECTOR_MAX_UPLOAD", MAX_UPLOAD_BYTES),
    )


def ensure_dirs(settings: Settings) -> None:
    """Create the directory tree the server writes into."""
    for path in (settings.data_dir, settings.books_dir, settings.audio_dir):
        path.mkdir(parents=True, exist_ok=True)
