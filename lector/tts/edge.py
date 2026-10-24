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
from lector.tts.mp3 import mp3_duration, trim_mp3

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
    # 后缀随音频格式变化：裁掉首尾静音后缓存键必须跟着变，
    # 否则旧的未裁剪句砖还会被命中。
    version = f"edge-tts-{edge_tts.__version__}.trim2"

    def __init__(self, timeout: float = 8.0) -> None:
        self.timeout = timeout
        #: How often a stalled sentence is retried inside the budget.
        self.attempts = 2

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
        """Synthesise one sentence and collect its word boundaries.

        The service occasionally stalls on a short sentence.  Rather than
        failing outright, the budget is split over a few attempts so a hiccup
        costs a retry instead of a 504.
        """
        clean = text.strip()
        if not clean:
            return TTSResult(audio=b"", duration=0.0, words=[], granularity="sentence")
        # 第一次尝试给足时间（多数句子在这里就成功了），
        # 剩下的预算平分给重试。
        first = self.timeout * 0.6
        budgets = [first] + [(self.timeout - first) / (self.attempts - 1)] * (
            self.attempts - 1
        )
        last_error: Exception | None = None
        for slice_timeout in budgets:
            try:
                return await self._synth_once(clean, voice, rate, slice_timeout)
            except (TTSTimeout, OSError) as exc:
                last_error = exc
                continue
        raise TTSTimeout(f"语音合成超时：{last_error or '引擎无响应'}")

    async def _synth_once(
        self, text: str, voice: str, rate: str, timeout: float
    ) -> TTSResult:
        """One synthesis attempt."""
        communicate = edge_tts.Communicate(
            text, voice, rate=rate, boundary="WordBoundary"
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

            await asyncio.wait_for(collect(), timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise TTSTimeout("语音合成超时") from exc
        except Exception as exc:  # noqa: BLE001 - engine errors are user facing
            raise TTSUnavailable(f"语音合成失败：{exc}") from exc

        words = align_boundaries(text, split_words(text), boundaries)
        audio_bytes, shift, duration = self._trim(bytes(audio), words)
        if shift:
            words = [
                (name, max(0.0, start - shift), max(0.0, end - shift))
                for name, start, end in words
            ]
        return TTSResult(
            audio=audio_bytes,
            duration=duration,
            words=[
                WordBoundary(text=name, start=start, end=end)
                for name, start, end in words
            ],
            granularity="word" if words else "sentence",
        )

    def _trim(
        self, audio: bytes, words: list[tuple[str, float, float]]
    ) -> tuple[bytes, float, float]:
        """Cut the silence around the speech.

        Every tile comes with a lead-in and a tail of silence.  Left in place
        they turn into a pause between every sentence, so they are removed.
        """
        if not audio or not words:
            return audio, 0.0, mp3_duration(audio)
        try:
            trimmed, shift, duration = trim_mp3(audio, words[0][1], words[-1][2])
        except Exception:  # noqa: BLE001 - trimming is an optimisation
            return audio, 0.0, mp3_duration(audio)
        if not trimmed:
            return audio, 0.0, mp3_duration(audio)
        return trimmed, shift, duration
