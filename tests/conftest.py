"""Shared fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lector.config import Settings, load_settings
from lector.epub.sentences import split_words
from lector.tts.base import TTSResult, Voice, WordBoundary

from factories import build_epub2, build_epub3, build_malicious_epub

REPO_ROOT = Path(__file__).resolve().parent.parent
BOOKS_DIR = REPO_ROOT / "books"


class FakeEngine:
    """A synthesis engine that answers without touching the network."""

    name = "fake"
    version = "fake-1"

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    async def voices(self) -> list[Voice]:
        return [
            Voice(
                voice_id="zh-CN-XiaoxiaoNeural",
                name="Xiaoxiao",
                locale="zh-CN",
                gender="female",
                engine=self.name,
            )
        ]

    async def synth(self, text: str, voice: str, rate: str = "+0%") -> TTSResult:
        self.calls.append((text, voice, rate))
        words = []
        cursor = 0.0
        for start, end in split_words(text):
            words.append(
                WordBoundary(text=text[start:end], start=cursor, end=cursor + 0.2)
            )
            cursor += 0.2
        return TTSResult(
            audio=b"ID3\x03\x00\x00\x00\x00\x00\x00fake-mp3",
            duration=max(cursor, 0.2),
            words=words,
            granularity="word" if words else "sentence",
        )


class FailingEngine(FakeEngine):
    """An engine that is not available."""

    async def voices(self) -> list[Voice]:
        from lector.tts.base import TTSUnavailable

        raise TTSUnavailable("引擎不可用")

    async def synth(self, text: str, voice: str, rate: str = "+0%") -> TTSResult:
        from lector.tts.base import TTSUnavailable

        raise TTSUnavailable("引擎不可用")


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Settings pointing at a temporary data directory."""
    config = load_settings(tmp_path / "data")
    return config


@pytest.fixture
def engine() -> FakeEngine:
    return FakeEngine()


@pytest.fixture
def client(settings: Settings, engine: FakeEngine) -> TestClient:
    """A test client with the fake engine wired in."""
    from lector.web import create_app

    app = create_app(settings)
    app.state.ctx.engine = engine
    app.state.ctx.audio.engine = engine
    return TestClient(app)


@pytest.fixture
def epub2_bytes() -> bytes:
    return build_epub2()


@pytest.fixture
def epub3_bytes() -> bytes:
    return build_epub3()


@pytest.fixture
def malicious_bytes() -> bytes:
    return build_malicious_epub()


@pytest.fixture
def real_epub_bytes() -> bytes:
    """A real EPUB from ``books/`` when the directory is not empty."""
    candidates = sorted(BOOKS_DIR.glob("*.epub"))
    if not candidates:
        pytest.skip("books/ 目录中没有 EPUB 文件")
    return candidates[0].read_bytes()
