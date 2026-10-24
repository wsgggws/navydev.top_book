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
