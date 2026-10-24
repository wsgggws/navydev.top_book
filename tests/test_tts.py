"""The TTS helpers: cache keys, durations and boundary alignment."""

from __future__ import annotations

from lector.epub.sentences import align_boundaries, split_words
from lector.tts.cache import cache_key
from lector.tts.mp3 import mp3_duration


def test_cache_key_depends_on_every_part():
    base = cache_key("hello", "voice", "+0%", "v1")
    assert base != cache_key("hello ", "voice", "+0%", "v1")
    assert base != cache_key("hello", "other", "+0%", "v1")
    assert base != cache_key("hello", "voice", "+10%", "v1")
    assert base != cache_key("hello", "voice", "+0%", "v2")
    assert base == cache_key("hello", "voice", "+0%", "v1")
    assert len(base) == 64


def test_mp3_duration_of_an_empty_stream_is_zero():
    assert mp3_duration(b"") == 0.0
    assert mp3_duration(b"not audio at all") == 0.0


def test_alignment_maps_boundaries_onto_words():
    text = "He left."
    words = split_words(text)
    boundaries = [("He", 0.1, 0.3), ("left", 0.35, 0.8)]
    aligned = align_boundaries(text, words, boundaries)
    assert [item[0] for item in aligned] == ["He", "left"]
    assert aligned[0][1] == 0.1
    assert aligned[1][2] == 0.8


def test_alignment_interpolates_inside_a_boundary():
    text = "玫瑰"
    words = split_words(text)
    boundaries = [("玫瑰", 0.0, 1.0)]
    aligned = align_boundaries(text, words, boundaries)
    assert len(aligned) == 2
    assert aligned[0][1] == 0.0
    # The words meet exactly where the first one ends.
    assert aligned[0][2] == aligned[1][1] == 0.5
    assert aligned[1][2] == 1.0


def test_alignment_skips_punctuation():
    text = "他说：“好。”"
    words = split_words(text)
    boundaries = [("他", 0.0, 0.2), ("说", 0.2, 0.4), ("好", 0.5, 0.8)]
    aligned = align_boundaries(text, words, boundaries)
    assert len(aligned) == len(words)
    assert [item[0] for item in aligned] == ["他", "说", "好"]


def test_trim_mp3_cuts_the_silence():
    """The lead-in and the tail of a tile are removed."""
    from lector.tts.mp3 import iter_frames, trim_mp3

    # 一段假的 MP3：MPEG1 Layer III, 64kbps, 44.1kHz
    header = bytes([0xFF, 0xFB, 0x50, 0xC4])
    frame_size = 144 * 64000 // 44100
    data = b"".join(header + b"\x00" * (frame_size - 4) for _ in range(100))
    assert len(iter_frames(data)) == 100

    trimmed, shift, duration = trim_mp3(data, 0.5, 1.5)
    assert shift > 0
    assert duration < 2.4
    assert len(trimmed) < len(data)


def test_trim_mp3_keeps_everything_when_there_is_nothing_to_cut():
    from lector.tts.mp3 import trim_mp3

    header = bytes([0xFF, 0xFB, 0x50, 0xC4])
    frame_size = 144 * 64000 // 44100
    data = header + b"\x00" * (frame_size - 4)
    trimmed, shift, duration = trim_mp3(data, 0.0, None)
    assert shift == 0.0
    assert len(trimmed) == len(data)


def test_engine_retries_a_stalled_sentence():
    """A synthesis that stalls is retried inside the time budget."""
    import asyncio

    from lector.tts.base import TTSResult, TTSTimeout
    from lector.tts.edge import EdgeTTSEngine

    class StallingEngine(EdgeTTSEngine):
        """Fails the first attempt, succeeds the second."""

        def __init__(self) -> None:
            super().__init__(timeout=4.0)
            self.calls = 0

        async def _synth_once(self, text, voice, rate, timeout):
            self.calls += 1
            if self.calls == 1:
                raise TTSTimeout("stalled")
            return TTSResult(audio=b"x", duration=1.0, words=[], granularity="sentence")

    engine = StallingEngine()

    async def scenario():
        result = await engine.synth("一句话", "zh-CN-XiaoxiaoNeural")
        assert result.duration == 1.0
        assert engine.calls == 2

    asyncio.run(scenario())


def test_engine_gives_up_after_the_budget():
    """When every attempt stalls the caller gets a timeout, not a hang."""
    import asyncio

    from lector.tts.base import TTSTimeout
    from lector.tts.edge import EdgeTTSEngine

    class AlwaysStalling(EdgeTTSEngine):
        async def _synth_once(self, text, voice, rate, timeout):
            raise TTSTimeout("stalled")

    engine = AlwaysStalling(timeout=4.0)

    async def scenario():
        try:
            await engine.synth("一句话", "zh-CN-XiaoxiaoNeural")
        except TTSTimeout:
            return
        raise AssertionError("应当抛出 TTSTimeout")

    asyncio.run(scenario())
