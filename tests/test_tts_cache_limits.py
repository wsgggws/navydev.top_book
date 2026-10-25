"""The public synthesiser must not grow disk storage without a bound."""

from __future__ import annotations

import pytest

from lector.tts import cache as cache_module
from lector.tts.base import TTSResult, TTSUnavailable
from lector.tts.cache import AudioCache, cache_key


def result(size: int = 200) -> TTSResult:
    return TTSResult(audio=b'x' * size, duration=1.0, words=[], granularity="sentence")


def disk_bytes(root) -> int:
    return sum(path.stat().st_size for path in root.rglob('*') if path.is_file())


def test_cache_evicts_least_recently_used_tile(tmp_path, monkeypatch):
    monkeypatch.setattr(cache_module, 'MAX_CACHE_BYTES', 700, raising=False)
    cache = AudioCache(tmp_path)
    keys = [cache_key(str(i), 'voice', '+0%', 'v1') for i in range(3)]
    cache.store(keys[0], result())
    cache.store(keys[1], result())
    assert cache.load(keys[0]) is not None
    cache.store(keys[2], result())
    assert disk_bytes(tmp_path) <= 700
    assert cache.load(keys[0]) is not None
    assert cache.load(keys[1]) is None
    assert cache.load(keys[2]) is not None
    assert not cache.meta_path(keys[1]).exists()


def test_existing_cache_is_trimmed_on_startup(tmp_path, monkeypatch):
    cache = AudioCache(tmp_path)
    for i in range(3):
        cache.store(cache_key(str(i), 'voice', '+0%', 'v1'), result())
    assert disk_bytes(tmp_path) > 700
    monkeypatch.setattr(cache_module, 'MAX_CACHE_BYTES', 700, raising=False)
    AudioCache(tmp_path)
    assert disk_bytes(tmp_path) <= 700


def test_oversized_tile_is_not_written(tmp_path, monkeypatch):
    monkeypatch.setattr(cache_module, 'MAX_CACHE_BYTES', 700, raising=False)
    cache = AudioCache(tmp_path)
    with pytest.raises(TTSUnavailable):
        cache.store(cache_key('huge', 'voice', '+0%', 'v1'), result(701))
    assert disk_bytes(tmp_path) == 0


def test_cache_can_be_repopulated_after_clear(tmp_path, monkeypatch):
    monkeypatch.setattr(cache_module, 'MAX_CACHE_BYTES', 700, raising=False)
    cache = AudioCache(tmp_path)
    key = cache_key('text', 'voice', '+0%', 'v1')
    cache.store(key, result())
    assert cache.clear() == 1
    cache.store(key, result())
    assert cache.load(key) is not None
    assert disk_bytes(tmp_path) <= 700


def test_eviction_removes_readiness_records(client, epub2_bytes, engine, monkeypatch):
    ctx = client.app.state.ctx
    ctx.cache._max_bytes = 700
    book_id = ctx.store.ingest(epub2_bytes).book.book_id
    ids = ctx.store.chapter_sentences(book_id, 'c0')[:3]
    async def synth(*args):
        return result()
    monkeypatch.setattr(engine, 'synth', synth)
    import asyncio
    async def scenario():
        for sentence_id in ids:
            assert await ctx.audio.tile(book_id, sentence_id, 'zh-CN-YunxiNeural') is not None
        assert disk_bytes(ctx.settings.audio_dir) <= 700
        assert not ctx.audio.has_tile(book_id, ids[0])
        assert ctx.audio.has_tile(book_id, ids[-1])
        assert ctx.audio.book_state(book_id) == 'partial'
    asyncio.run(scenario())


def test_constructor_explicit_limit_overrides_constant(tmp_path, monkeypatch):
    monkeypatch.setattr(cache_module, 'MAX_CACHE_BYTES', 100, raising=False)
    cache = AudioCache(tmp_path, max_bytes=700)
    cache.store(cache_key('text', 'voice', '+0%', 'v1'), result())
    assert disk_bytes(tmp_path) <= 700


def test_constructor_none_uses_patched_constant(tmp_path, monkeypatch):
    monkeypatch.setattr(cache_module, 'MAX_CACHE_BYTES', 700, raising=False)
    cache = AudioCache(tmp_path, max_bytes=None)
    for i in range(3):
        cache.store(cache_key(str(i), 'voice', '+0%', 'v1'), result())
    assert disk_bytes(tmp_path) <= 700


@pytest.mark.parametrize('raw,expected', [
    (None, 10 * 1024**3), ('', 10 * 1024**3), ('invalid', 10 * 1024**3),
    ('0', 10 * 1024**3), ('-1', 10 * 1024**3), ('4096', 4096),
])
def test_cache_capacity_setting(tmp_path, monkeypatch, raw, expected):
    from lector.config import load_settings
    if raw is None:
        monkeypatch.delenv('LECTOR_AUDIO_CACHE_BYTES', raising=False)
    else:
        monkeypatch.setenv('LECTOR_AUDIO_CACHE_BYTES', raw)
    assert load_settings(tmp_path).audio_cache_bytes == expected


def test_app_passes_configured_capacity_to_cache(settings):
    from dataclasses import replace
    from lector.web import create_app
    app = create_app(replace(settings, audio_cache_bytes=700))
    assert app.state.ctx.cache._max_bytes == 700
