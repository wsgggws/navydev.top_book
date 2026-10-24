"""Text to speech."""

from lector.tts.base import (
    TTSEngine,
    TTSError,
    TTSResult,
    TTSTimeout,
    TTSUnavailable,
    Voice,
    WordBoundary,
)
from lector.tts.cache import AudioCache, CachedTile, cache_key

__all__ = [
    "AudioCache",
    "CachedTile",
    "TTSEngine",
    "TTSError",
    "TTSResult",
    "TTSTimeout",
    "TTSUnavailable",
    "Voice",
    "WordBoundary",
    "cache_key",
]
