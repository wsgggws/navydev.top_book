"""Playing a sentence tile in the terminal.

The terminal does not stream: it downloads one sentence, hands the file to a
system player and watches the clock, so the word highlight can follow the
voice.  Several players are supported because no single one exists everywhere.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

#: Players in the order they are tried.
BACKENDS = ("afplay", "ffplay", "aplay", "mpv")


def find_backend() -> str | None:
    """The system player that is available."""
    for name in BACKENDS:
        if shutil.which(name):
            return name
    return None


@dataclass
class AudioPlayer:
    """Plays local audio files with a system command."""

    backend: str | None = None
    rate: float = 1.0
    effective_rate: float = 1.0
    workdir: Path | None = None
    _process: subprocess.Popen | None = None
    _tempdir: str | None = None

    def __post_init__(self) -> None:
        if self.backend is None:
            self.backend = find_backend()

    @property
    def available(self) -> bool:
        return self.backend is not None

    def _command(self, path: str, rate: float = 1.0) -> list[str]:
        backend = self.backend or ""
        if backend == "afplay":
            return ["afplay", "-r", str(rate), "-q", "1", path]
        if backend == "ffplay":
            return ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet",
                    "-af", f"atempo={rate}", path]
        if backend == "aplay":
            return ["aplay", "-q", path]
        if backend == "mpv":
            return ["mpv", "--no-video", "--really-quiet", f"--speed={rate}", path]
        return []

    def _adjust_rate(self, source: str) -> str:
        """Bake a speed change into the file when the rate is not 1.0."""
        if abs(self.rate - 1.0) < 0.01:
            return source
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            return source
        target = str(Path(source).with_name(Path(source).stem + "-rate.mp3"))
        command = [
            ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
            "-i", source, "-filter:a", f"atempo={self.rate}", target,
        ]
        try:
            subprocess.run(command, check=True, capture_output=True, timeout=60)
        except (subprocess.SubprocessError, OSError):
            return source
        return target

    def play(self, path: str) -> None:
        """Start playing a file."""
        self.stop()
        if not self.available:
            raise RuntimeError("没有可用的音频播放器")
        adjusted = self._adjust_rate(path)
        native_rate = self.rate if adjusted == path else 1.0
        if self.backend == "aplay" and abs(native_rate - 1) >= 0.01:
            raise RuntimeError("aplay 倍速播放需要 ffmpeg，请安装 ffmpeg 或改用 mpv")
        self.effective_rate = self.rate
        self._process = subprocess.Popen(
            self._command(adjusted, native_rate),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def wait(self, timeout: float | None = None) -> bool:
        """Block until the file finished playing."""
        if self._process is None:
            return True
        try:
            self._process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            return False
        return True

    def stop(self) -> None:
        """Stop whatever is playing."""
        if self._process is not None and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._process.kill()
        self._process = None

    def tempdir(self) -> Path:
        """A directory for the downloaded tiles."""
        if self.workdir is None:
            self._tempdir = tempfile.mkdtemp(prefix="lector-")
            self.workdir = Path(self._tempdir)
        return self.workdir

    def cleanup(self) -> None:
        """Stop and remove the temporary files."""
        self.stop()
        if self.workdir and self.workdir.exists():
            shutil.rmtree(self.workdir, ignore_errors=True)
        self.workdir = None


def format_time(seconds: float) -> str:
    """``mm:ss`` — hours only when they are needed."""
    seconds = max(0, int(seconds))
    minutes, rest = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{rest:02d}"
    return f"{minutes:02d}:{rest:02d}"


class Clock:
    """A monotonic clock used to follow the word highlight."""

    def __init__(self) -> None:
        self.started = time.monotonic()

    def reset(self) -> None:
        self.started = time.monotonic()

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.started
