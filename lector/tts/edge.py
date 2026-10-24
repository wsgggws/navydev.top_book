"""The ``edge-tts`` engine.

Microsoft Edge's read-aloud voices are free, need no key and — crucially for
this project — report word boundaries, which is what the karaoke highlight is
built on.
"""

from __future__ import annotations

import asyncio

import edge_tts

from lector.epub.sentences import align_boundaries, split_words
from lector.tts.base import TTSResult, TTSTimeout, TTSUnavailable, Voice, WordBoundary
from lector.tts.mp3 import mp3_duration

#: edge-tts reports timings in 100-nanosecond ticks.
TICKS_PER_SECOND = 10_000_000


def _short_name(voice_id: str) -> str:
    """``zh-CN-XiaoxiaoNeural`` → ``Xiaoxiao``."""
    name = voice_id.split("-", 2)[-1] if voice_id.count("-") >= 2 else voice_id
    if name.endswith("Neural"):
        name = name[: -len("Neural")]
    return name or voice_id


class EdgeTTSEngine:
    """Synthesis through Microsoft Edge's online voices."""

    name = "edge"
    version = f"edge-tts-{edge_tts.__version__}"

    def __init__(self, timeout: float = 8.0) -> None:
        self.timeout = timeout

    async def voices(self) -> list[Voice]:
        """List the available voices."""
        try:
            raw = await asyncio.wait_for(edge_tts.list_voices(), timeout=self.timeout * 3)
        except Exception as exc:  # noqa: BLE001 - any failure means "no voices"
            raise TTSUnavailable(f"无法获取音色列表：{exc}") from exc
        voices = [
            Voice(
                voice_id=item.get("ShortName", ""),
                name=_short_name(item.get("ShortName", "")),
                locale=item.get("Locale", ""),
                gender=item.get("Gender", "").strip().lower(),
                engine=self.name,
            )
            for item in raw
        ]
        voices.sort(key=lambda v: (v.locale, v.name))
        return voices

    async def synth(self, text: str, voice: str, rate: str = "+0%") -> TTSResult:
        """Synthesise one sentence and collect its word boundaries."""
        clean = text.strip()
        if not clean:
            return TTSResult(audio=b"", duration=0.0, words=[], granularity="sentence")
        communicate = edge_tts.Communicate(
            clean, voice, rate=rate, boundary="WordBoundary"
        )
        audio = bytearray()
        boundaries: list[tuple[str, float, float]] = []
        try:
            async def collect() -> None:
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        audio.extend(chunk["data"])
                    elif chunk["type"] == "WordBoundary":
                        start = chunk["offset"] / TICKS_PER_SECOND
                        end = (chunk["offset"] + chunk["duration"]) / TICKS_PER_SECOND
                        boundaries.append((chunk["text"], start, end))

            await asyncio.wait_for(collect(), timeout=self.timeout)
        except asyncio.TimeoutError as exc:
            raise TTSTimeout("语音合成超时") from exc
        except Exception as exc:  # noqa: BLE001 - engine errors are user facing
            raise TTSUnavailable(f"语音合成失败：{exc}") from exc

        duration = mp3_duration(bytes(audio))
        words = [
            WordBoundary(text=name, start=start, end=end)
            for name, start, end in align_boundaries(
                clean, split_words(clean), boundaries
            )
        ]
        return TTSResult(
            audio=bytes(audio),
            duration=duration,
            words=words,
            granularity="word" if words else "sentence",
        )
