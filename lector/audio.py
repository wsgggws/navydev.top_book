"""Audio tiles: synthesis, caching and voice selection.

A *tile* is the audio of exactly one sentence plus the timing of its words.
Tiles are the unit of playback everywhere, which is what makes "click a
sentence, hear it" work.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

from lector.config import DEFAULT_VOICE_BY_LOCALE, FEATURED_VOICES, Settings
from lector.store import Store
from lector.tts.base import TTSEngine, TTSUnavailable, Voice
from lector.tts.cache import AudioCache, CachedTile, cache_key

#: Silence inserted between two tiles of a chapter timeline.
INTER_SENTENCE_GAP = 0.0

#: How long a voice list stays usable before it is fetched again.
VOICE_CACHE_TTL = 300.0


@dataclass
class VoiceChoice:
    """The voice a book is read with."""

    voice_id: str
    rate: str = "+0%"


class AudioService:
    """Produces and caches sentence tiles."""

    def __init__(
        self,
        settings: Settings,
        store: Store,
        cache: AudioCache,
        engine: TTSEngine,
    ) -> None:
        self.settings = settings
        self.store = store
        self.cache = cache
        self.engine = engine
        self._locks: dict[str, asyncio.Lock] = {}
        self._voices: list[Voice] = []
        self._voices_at = 0.0

    # -- voices ----------------------------------------------------------
    async def voices(self) -> list[Voice]:
        """The engine's voice list, cached for a few minutes."""
        now = time.monotonic()
        if self._voices and now - self._voices_at < VOICE_CACHE_TTL:
            return self._voices
        voices = await self.engine.voices()
        self._voices = voices
        self._voices_at = now
        return voices

    async def choose_voice(self, language: str | None, preferred: str | None) -> str:
        """Pick the voice a book should be read with.

        An explicitly chosen voice always wins.  Otherwise the book's language
        decides: a Chinese book is read in Chinese, an English book in
        American English, and the locale's default voice is used when the
        engine knows one.
        """
        if preferred:
            return preferred
        fallback = self.settings.default_voice
        if not language:
            return fallback
        prefix = language.split("-")[0].lower()
        wanted = DEFAULT_VOICE_BY_LOCALE.get(prefix)
        try:
            voices = await self.voices()
        except TTSUnavailable:
            return wanted or fallback
        available = {voice.voice_id for voice in voices}
        if wanted and wanted in available:
            return wanted
        # 常用音色优先，其次是引擎里任何同语言的声音。
        featured = [v for v in voices if v.voice_id in FEATURED_VOICES]
        for voice in featured:
            if voice.locale.split("-")[0].lower() == prefix:
                return voice.voice_id
        for voice in voices:
            if voice.locale.split("-")[0].lower() == prefix:
                return voice.voice_id
        return wanted or fallback

    # -- tiles -----------------------------------------------------------
    async def tile(
        self, book_id: str, sentence_id: str, voice_id: str, rate: str = "+0%"
    ) -> CachedTile | None:
        """Return the tile for a sentence, synthesising it when needed."""
        text = self.store.sentence_text(book_id, sentence_id)
        if text is None:
            return None
        key = cache_key(text.strip(), voice_id, rate, self.engine.version)
        cached = self.cache.load(key)
        if cached is not None:
            self._record_tile(book_id, sentence_id, key, voice_id, rate, cached)
            return cached
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            cached = self.cache.load(key)
            if cached is not None:
                self._record_tile(book_id, sentence_id, key, voice_id, rate, cached)
                return cached
            result = await self.engine.synth(text, voice_id, rate)
            self.cache.store(key, result)
            cached = CachedTile(
                audio=result.audio,
                duration=result.duration,
                words=result.words,
                granularity=result.granularity,
            )
            self._record_tile(book_id, sentence_id, key, voice_id, rate, cached)
            return cached

    def _record_tile(
        self,
        book_id: str,
        sentence_id: str,
        key: str,
        voice_id: str,
        rate: str,
        tile: CachedTile,
    ) -> None:
        """Remember which tile a sentence currently uses."""
        from lector.store import utcnow

        with self.store.db.write() as conn:
            conn.execute(
                """
                INSERT INTO audio_tiles (book_id, sentence_id, cache_key, voice_id, rate,
                                         duration, granularity, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(book_id, sentence_id) DO UPDATE SET
                    cache_key = excluded.cache_key,
                    voice_id = excluded.voice_id,
                    rate = excluded.rate,
                    duration = excluded.duration,
                    granularity = excluded.granularity
                """,
                (
                    book_id,
                    sentence_id,
                    key,
                    voice_id,
                    rate,
                    tile.duration,
                    tile.granularity,
                    utcnow(),
                ),
            )

    def has_tile(self, book_id: str, sentence_id: str) -> bool:
        row = self.store.db.query_one(
            "SELECT 1 FROM audio_tiles WHERE book_id = ? AND sentence_id = ?",
            (book_id, sentence_id),
        )
        return row is not None

    def tile_duration(self, book_id: str, sentence_id: str) -> float | None:
        row = self.store.db.query_one(
            "SELECT duration FROM audio_tiles WHERE book_id = ? AND sentence_id = ?",
            (book_id, sentence_id),
        )
        return float(row["duration"]) if row else None

    def clear_book(self, book_id: str) -> None:
        """Forget every tile of a book (the files stay in the shared cache)."""
        with self.store.db.write() as conn:
            conn.execute("DELETE FROM audio_tiles WHERE book_id = ?", (book_id,))

    def book_state(self, book_id: str) -> str:
        """``pending`` / ``partial`` / ``ready`` for a book."""
        total = self.store.db.query_one(
            "SELECT COUNT(*) AS n FROM sentences WHERE book_id = ?", (book_id,)
        )
        ready = self.store.db.query_one(
            "SELECT COUNT(*) AS n FROM audio_tiles WHERE book_id = ?", (book_id,)
        )
        total_count = int(total["n"]) if total else 0
        ready_count = int(ready["n"]) if ready else 0
        if total_count == 0 or ready_count == 0:
            return "pending"
        if ready_count >= total_count:
            return "ready"
        return "partial"
