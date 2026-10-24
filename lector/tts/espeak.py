"""Offline fallback engine.

``espeak-ng`` is not installed everywhere, and it reports no word boundaries,
so the fallback degrades to sentence granularity — the client then highlights
whole sentences instead of words.
"""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from pathlib import Path

from lector.tts.base import TTSResult, TTSUnavailable, Voice

#: Edge locales mapped onto espeak voices.
_LOCALE_ALIASES = {
    "zh": "cmn",
    "ja": "ja",
    "ko": "ko",
    "en": "en",
    "de": "de",
    "fr": "fr",
    "es": "es",
    "ru": "ru",
    "pt": "pt",
    "it": "it",
    "hi": "hi",
    "ar": "ar",
}


def _find_binary() -> str | None:
    for name in ("espeak-ng", "espeak"):
        path = shutil.which(name)
        if path:
            return path
    return None


class EspeakEngine:
    """Synthesis through the local ``espeak-ng`` binary."""

    name = "espeak"
    version = "espeak-ng-1"

    def __init__(self, timeout: float = 8.0) -> None:
        self.timeout = timeout
        self.binary = _find_binary()

    @property
    def available(self) -> bool:
        return self.binary is not None

    async def voices(self) -> list[Voice]:
        """espeak exposes one voice per language, not per speaker."""
        if not self.available:
            raise TTSUnavailable("未安装 espeak-ng，无法列出音色")
        voices = [
            Voice(voice_id=f"espeak-{code}", name=code, locale=code, gender="neutral", engine=self.name)
            for code in sorted(_LOCALE_ALIASES.values())
        ]
        return voices

    async def synth(self, text: str, voice: str, rate: str = "+0%") -> TTSResult:
        """Synthesise one sentence into MP3."""
        if not self.available:
            raise TTSUnavailable("未安装 espeak-ng，无法合成语音")
        clean = text.strip()
        if not clean:
            return TTSResult(audio=b"", duration=0.0, words=[], granularity="sentence")
        locale = voice.split("-")[0].lower()
        espeak_voice = _LOCALE_ALIASES.get(locale, locale or "en")
        words_per_minute = _rate_to_wpm(rate)
        with tempfile.TemporaryDirectory() as workdir:
            wav_path = Path(workdir) / "tile.wav"
            mp3_path = Path(workdir) / "tile.mp3"
            command = [
                self.binary,
                "-v", espeak_voice,
                "-s", str(words_per_minute),
                "-w", str(wav_path),
                "--", clean,
            ]
            try:
                proc = await asyncio.create_subprocess_exec(
                    *command,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.PIPE,
                )
                _, stderr = await asyncio.wait_for(proc.communicate(), timeout=self.timeout)
            except asyncio.TimeoutError as exc:
                raise TTSUnavailable("语音合成超时") from exc
            except OSError as exc:
                raise TTSUnavailable(f"语音合成失败：{exc}") from exc
            if proc.returncode != 0 or not wav_path.exists():
                detail = stderr.decode("utf-8", "replace").strip()[:200]
                raise TTSUnavailable(f"语音合成失败：{detail or 'espeak-ng 返回错误'}")
            audio = await self._to_mp3(wav_path, mp3_path)
        from lector.tts.mp3 import mp3_duration

        return TTSResult(
            audio=audio,
            duration=mp3_duration(audio),
            words=[],
            granularity="sentence",
        )

    async def _to_mp3(self, wav_path: Path, mp3_path: Path) -> bytes:
        """Convert the rendered WAV into MP3 with ffmpeg."""
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise TTSUnavailable("缺少 ffmpeg，无法把 espeak 音频转为 mp3")
        command = [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(wav_path), "-codec:a", "libmp3lame", "-b:a", "48k", str(mp3_path),
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *command, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=self.timeout)
        except asyncio.TimeoutError as exc:
            raise TTSUnavailable("音频转码超时") from exc
        except OSError as exc:
            raise TTSUnavailable(f"音频转码失败：{exc}") from exc
        if proc.returncode != 0 or not mp3_path.exists():
            detail = stderr.decode("utf-8", "replace").strip()[:200]
            raise TTSUnavailable(f"音频转码失败：{detail}")
        return mp3_path.read_bytes()


def _rate_to_wpm(rate: str) -> int:
    """Translate an edge-style percentage rate into espeak words per minute."""
    try:
        percent = int(rate.strip().rstrip("%"))
    except ValueError:
        percent = 0
    return max(80, min(450, int(175 * (1 + percent / 100))))
