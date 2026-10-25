"""Content addressed cache for synthesised sentence tiles.

The key is ``sha256(text | voice | rate | engine_version)``, so the same
sentence with the same settings is synthesised exactly once — no matter which
book, device or endpoint asked for it.
"""

from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from lector.config import DEFAULT_AUDIO_CACHE_BYTES
from lector.tts.base import TTSResult, TTSUnavailable, WordBoundary

MAX_CACHE_BYTES = DEFAULT_AUDIO_CACHE_BYTES


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

    def __init__(
        self,
        root: Path,
        max_bytes: int | None = None,
        on_evict: Callable[[str], None] | None = None,
    ) -> None:
        self.root = Path(root)
        self._on_evict = on_evict
        self._entries: OrderedDict[str, int] = OrderedDict()
        self._used_bytes = 0
        self._max_bytes = MAX_CACHE_BYTES if max_bytes is None else max_bytes
        if self._max_bytes <= 0:
            raise ValueError("音频缓存容量必须是正整数字节数")
        # Reconstruct once; rescanning every sentence would make a large book
        # quadratic to synthesise. The built-in server owns one cache process.
        files: dict[str, tuple[int, float]] = {}
        for path in self.root.rglob("*"):
            if path.suffix not in (".mp3", ".json") or not path.is_file():
                continue
            stat = path.stat()
            size, modified = files.get(path.stem, (0, 0.0))
            files[path.stem] = (size + stat.st_size, max(modified, stat.st_mtime))
        for key, (size, _) in sorted(files.items(), key=lambda item: item[1][1]):
            self._entries[key] = size
            self._used_bytes += size
        self._make_room(0)

    def _make_room(self, needed: int) -> None:
        while self._entries and self._used_bytes + needed > self._max_bytes:
            key = next(iter(self._entries))
            if self._on_evict is not None:
                self._on_evict(key)
            self.audio_path(key).unlink(missing_ok=True)
            self.meta_path(key).unlink(missing_ok=True)
            self._used_bytes -= self._entries.pop(key)

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
        if key in self._entries:
            self._entries.move_to_end(key)
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
        meta = {
            "duration": result.duration,
            "granularity": result.granularity,
            "words": [{"text": w.text, "start": w.start, "end": w.end} for w in result.words],
        }
        encoded_meta = json.dumps(meta, ensure_ascii=False).encode("utf-8")
        size = len(result.audio) + len(encoded_meta)
        if size > self._max_bytes:
            raise TTSUnavailable("单句音频超过缓存容量上限")
        previous = self._entries.pop(key, 0)
        self._used_bytes -= previous
        self._make_room(size)
        audio_path.parent.mkdir(parents=True, exist_ok=True)
        audio_tmp = audio_path.with_suffix(".mp3.tmp")
        meta_tmp = meta_path.with_suffix(".json.tmp")
        try:
            audio_tmp.write_bytes(result.audio)
            meta_tmp.write_bytes(encoded_meta)
            audio_tmp.replace(audio_path)
            meta_tmp.replace(meta_path)
        finally:
            audio_tmp.unlink(missing_ok=True)
            meta_tmp.unlink(missing_ok=True)
        self._entries[key] = size
        self._used_bytes += size

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
        self._entries.clear()
        self._used_bytes = 0
        return removed
