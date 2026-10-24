"""Content addressed cache for synthesised sentence tiles.

The key is ``sha256(text | voice | rate | engine_version)``, so the same
sentence with the same settings is synthesised exactly once — no matter which
book, device or endpoint asked for it.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from lector.tts.base import TTSResult, WordBoundary


@dataclass
class CachedTile:
    """A synthesised sentence tile."""

    audio: bytes
    duration: float
    words: list[WordBoundary]
    granularity: str


def cache_key(text: str, voice: str, rate: str, engine_version: str) -> str:
    """The cache key of one tile."""
    digest = hashlib.sha256()
    digest.update(text.encode("utf-8"))
    digest.update(b"\x00")
    digest.update(voice.encode("utf-8"))
    digest.update(b"\x00")
    digest.update(rate.encode("utf-8"))
    digest.update(b"\x00")
    digest.update(engine_version.encode("utf-8"))
    return digest.hexdigest()


class AudioCache:
    """Stores tiles under ``<root>/<key[:2]>/<key>.{mp3,json}``."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def audio_path(self, key: str) -> Path:
        return self.root / key[:2] / f"{key}.mp3"

    def meta_path(self, key: str) -> Path:
        return self.root / key[:2] / f"{key}.json"

    def load(self, key: str) -> CachedTile | None:
        """Return the cached tile, or ``None`` when it is not cached."""
        audio_path = self.audio_path(key)
        meta_path = self.meta_path(key)
        if not audio_path.exists() or not meta_path.exists():
            return None
        try:
            meta = json.loads(meta_path.read_text("utf-8"))
            audio = audio_path.read_bytes()
        except (OSError, ValueError):
            return None
        words = [WordBoundary(**item) for item in meta.get("words", [])]
        return CachedTile(
            audio=audio,
            duration=float(meta.get("duration", 0.0)),
            words=words,
            granularity=meta.get("granularity", "sentence"),
        )

    def store(self, key: str, result: TTSResult) -> None:
        """Write a synthesised tile to the cache."""
        audio_path = self.audio_path(key)
        meta_path = self.meta_path(key)
        audio_path.parent.mkdir(parents=True, exist_ok=True)
        audio_path.write_bytes(result.audio)
        meta = {
            "duration": result.duration,
            "granularity": result.granularity,
            "words": [{"text": w.text, "start": w.start, "end": w.end} for w in result.words],
        }
        tmp = meta_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(meta, ensure_ascii=False), "utf-8")
        tmp.replace(meta_path)

    def clear(self) -> int:
        """Remove every cached tile and return how many were deleted."""
        removed = 0
        if not self.root.exists():
            return 0
        for path in self.root.rglob("*.mp3"):
            path.unlink(missing_ok=True)
            removed += 1
        for path in self.root.rglob("*.json"):
            path.unlink(missing_ok=True)
        return removed
