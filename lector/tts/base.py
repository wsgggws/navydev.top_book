"""The TTS engine interface.

An engine turns text into audio plus the timing information the karaoke
highlight needs.  When an engine cannot provide word boundaries it degrades to
sentence granularity instead of failing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

# The voice record is part of the API contract, so it has exactly one definition.
from lector.models import Voice


@dataclass
class WordBoundary:
    """Timing of a word relative to the start of its sentence."""

    text: str
    start: float
    end: float


@dataclass
class TTSResult:
    """What an engine returns for one sentence."""

    audio: bytes
    duration: float
    words: list[WordBoundary] = field(default_factory=list)
    granularity: str = "word"


class TTSError(Exception):
    """Base class for engine failures."""


class TTSUnavailable(TTSError):
    """The engine cannot be reached or is not installed."""


class TTSTimeout(TTSError):
    """The engine did not answer in time."""


@runtime_checkable
class TTSEngine(Protocol):
    """What every engine must provide."""

    name: str
    version: str

    async def voices(self) -> list[Voice]: ...

    async def synth(self, text: str, voice: str, rate: str) -> TTSResult: ...
