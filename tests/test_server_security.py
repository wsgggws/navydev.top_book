"""Regression coverage for server trust boundaries and public resource use."""

from __future__ import annotations

import asyncio
import time
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from lector.web import create_app


def make_client(settings, engine, *, peer="127.0.0.1", **changes):
    app = create_app(replace(settings, **changes))
    app.state.ctx.engine = engine
    app.state.ctx.audio.engine = engine
    return TestClient(app, base_url="http://localhost", client=(peer, 50000))


@pytest.mark.parametrize("base", ["", "/ebook"])
@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "[::1]", "testserver"])
def test_remote_host_spoof_cannot_enable_admin(settings, engine, epub2_bytes, base, host):
    client = make_client(settings, engine, peer="203.0.113.9", base_path=base, token="")
    response = client.post(
        f"{base}/api/v1/books",
        headers={"Host": host, "Origin": f"http://{host}", "User-Agent": "Mozilla/5.0"},
        files={"file": ("book.epub", epub2_bytes)},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ADMIN_DISABLED"
    assert client.app.state.ctx.store.count_books() == 0


@pytest.mark.parametrize("headers", [
    {"X-Forwarded-For": "203.0.113.9"},
    {"Forwarded": 'for=203.0.113.9;host=localhost'},
])
def test_proxied_loopback_is_not_local_development(settings, engine, epub2_bytes, headers):
    client = make_client(settings, engine, token="")
    response = client.post(
        "/api/v1/books", files={"file": ("book.epub", epub2_bytes)},
        headers={**headers, "Origin": "http://localhost", "User-Agent": "Mozilla/5.0"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ADMIN_DISABLED"


def test_public_bind_disables_local_admin_exception(settings, engine, epub2_bytes):
    client = make_client(settings, engine, host="0.0.0.0", token="")
    response = client.post(
        "/api/v1/books", files={"file": ("book.epub", epub2_bytes)},
        headers={"Origin": "http://localhost", "User-Agent": "Mozilla/5.0"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ADMIN_DISABLED"


def test_local_browser_cannot_write_cross_origin(settings, engine, epub2_bytes):
    client = make_client(settings, engine, token="")
    response = client.post(
        "/api/v1/books", files={"file": ("book.epub", epub2_bytes)},
        headers={"Origin": "https://evil.example", "Sec-Fetch-Site": "cross-site"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "SAME_ORIGIN_REQUIRED"


@pytest.mark.parametrize("origin", ["https://localhost", "http://[broken"])
def test_origin_includes_scheme_and_handles_malformed_urls(settings, engine, epub2_bytes, origin):
    client = make_client(settings, engine, token="secret")
    book_id = client.app.state.ctx.store.ingest(epub2_bytes).book.book_id
    response = client.post(
        f"/api/v1/books/{book_id}/open",
        headers={"Origin": origin, "User-Agent": "Mozilla/5.0"},
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "SAME_ORIGIN_REQUIRED"


def test_non_ascii_bearer_is_rejected_without_crashing(settings, engine):
    client = make_client(settings, engine, token="secret")
    response = client.get(
        "/api/v1/books", headers={"authorization": b"Bearer \xff", "User-Agent": "Mozilla/5.0"},
    )
    assert response.status_code == 200  # Public reads still work with an invalid token.


def test_forwarded_header_cannot_reset_read_budget(settings, engine, monkeypatch):
    client = make_client(settings, engine)
    client.app.state.ctx.limiter.check("read", "127.0.0.1", 1)
    from lector.api import deps
    monkeypatch.setattr(deps, "READ_LIMIT", 1)
    response = client.get("/api/v1/books", headers={"X-Forwarded-For": "198.51.100.8"})
    assert response.status_code == 429
    assert int(response.headers["retry-after"]) > 0


def test_cover_cannot_read_parent_directory(client, settings):
    (settings.data_dir / "cover.bin").write_bytes(b"private-file")
    response = client.get("/api/v1/books/%2e%2e/cover")
    assert response.status_code == 404
    assert b"private-file" not in response.content


def test_cover_requires_a_registered_book(client, settings):
    orphan = settings.books_dir / "b_deadbeef"
    orphan.mkdir()
    (orphan / "cover.bin").write_bytes(b"private-orphan")
    assert client.get("/api/v1/books/b_deadbeef/cover").status_code == 404


def test_cover_symlink_cannot_escape_book(client, settings, epub2_bytes):
    ctx = client.app.state.ctx
    book_id = ctx.store.ingest(epub2_bytes).book.book_id
    secret = settings.data_dir / "private.bin"
    secret.write_bytes(b"private-file")
    (ctx.store.book_dir(book_id) / "cover.bin").symlink_to(secret)
    assert client.get(f"/api/v1/books/{book_id}/cover").status_code == 404


def test_chapter_symlink_cannot_read_external_json(client, settings, epub2_bytes):
    ctx = client.app.state.ctx
    book_id = ctx.store.ingest(epub2_bytes).book.book_id
    chapter = ctx.store.chapter_path(book_id, "c0")
    external = settings.data_dir / "external.json"
    external.write_bytes(chapter.read_bytes())
    chapter.unlink()
    chapter.symlink_to(external)
    assert client.get(f"/api/v1/books/{book_id}/chapters/c0").status_code == 404


def test_media_only_serves_images(client, epub2_bytes):
    book_id = client.app.state.ctx.store.ingest(epub2_bytes).book.book_id
    response = client.get(f"/api/v1/books/{book_id}/media/OEBPS/content.opf")
    assert response.status_code == 404


def test_media_rejects_oversized_member_before_decompression(client, epub2_bytes, monkeypatch):
    import zipfile
    from lector.api import books

    book_id = client.app.state.ctx.store.ingest(epub2_bytes).book.book_id
    monkeypatch.setattr(books, "MAX_MEDIA_BYTES", 8, raising=False)
    def forbidden_read(*args, **kwargs):
        raise AssertionError("oversized ZIP member must not be decompressed")
    monkeypatch.setattr(zipfile.ZipFile, "read", forbidden_read)
    response = client.get(f"/api/v1/books/{book_id}/media/OEBPS/text/images/f1.jpg")
    assert response.status_code == 404


@pytest.mark.parametrize("kind", ["mp3", "words", "warm"])
@pytest.mark.parametrize("options", [{"voice_id": "invented-voice"}, {"rate": "+999999%"}, {"rate": "NaN"}])
def test_audio_rejects_cache_busting_options(client, epub2_bytes, engine, kind, options):
    ctx = client.app.state.ctx
    book_id = ctx.store.ingest(epub2_bytes).book.book_id
    sentence_id = ctx.store.chapter_sentences(book_id, "c0")[0]
    if kind == "warm":
        response = client.post(f"/api/v1/books/{book_id}/audio/warm", json={"chapter_id": "c0", **options})
    else:
        response = client.get(f"/api/v1/books/{book_id}/audio/{sentence_id}.{kind}", params=options)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert engine.calls == []
    assert not list(ctx.settings.audio_dir.rglob("*.mp3"))


def test_equivalent_rates_reuse_cache(client, epub2_bytes, engine):
    ctx = client.app.state.ctx
    book_id = ctx.store.ingest(epub2_bytes).book.book_id
    sentence_id = ctx.store.chapter_sentences(book_id, "c0")[0]
    url = f"/api/v1/books/{book_id}/audio/{sentence_id}.mp3"
    assert client.get(url, params={"rate": "+0%"}).status_code == 200
    assert client.get(url, params={"rate": "+000%"}).status_code == 200
    assert len(engine.calls) == 1
    assert not ctx.audio._locks


def test_same_key_concurrency_deduplicates_and_releases_locks(client, epub2_bytes, engine):
    ctx = client.app.state.ctx
    book_id = ctx.store.ingest(epub2_bytes).book.book_id
    sentence_id = ctx.store.chapter_sentences(book_id, "c0")[0]
    original = engine.synth
    async def slow_synth(*args):
        await asyncio.sleep(0.01)
        return await original(*args)
    engine.synth = slow_synth
    async def scenario():
        tiles = await asyncio.gather(*[
            ctx.audio.tile(book_id, sentence_id, "zh-CN-YunxiNeural") for _ in range(8)
        ])
        assert all(tile is not None for tile in tiles)
        assert len(engine.calls) == 1
        assert not ctx.audio._locks
    asyncio.run(scenario())


def test_failed_synthesis_releases_locks(client, epub2_bytes, engine):
    from lector.tts.base import TTSUnavailable
    ctx = client.app.state.ctx
    book_id = ctx.store.ingest(epub2_bytes).book.book_id
    sentence_id = ctx.store.chapter_sentences(book_id, "c0")[0]
    async def fail(*args):
        raise TTSUnavailable("offline")
    engine.synth = fail
    async def scenario():
        with pytest.raises(TTSUnavailable):
            await ctx.audio.tile(book_id, sentence_id, "zh-CN-YunxiNeural")
        assert not ctx.audio._locks
    asyncio.run(scenario())


def test_search_sql_metacharacters_are_literal(client, epub2_bytes):
    book_id = client.app.state.ctx.store.ingest(epub2_bytes).book.book_id
    response = client.get(f"/api/v1/books/{book_id}/search", params={"q": "' OR 1=1 --"})
    assert response.status_code == 200
    assert response.json()["total"] == 0


def test_featured_cache_hit_does_not_fetch_voices(client, epub2_bytes, engine):
    from lector.tts.base import TTSUnavailable
    ctx = client.app.state.ctx
    book_id = ctx.store.ingest(epub2_bytes).book.book_id
    sentence_id = ctx.store.chapter_sentences(book_id, "c0")[0]
    url = f"/api/v1/books/{book_id}/audio/{sentence_id}.mp3"
    options = {"voice_id": "zh-CN-YunxiNeural", "rate": "+0%"}
    original = client.get(url, params=options)
    assert original.status_code == 200
    ctx.audio._voices = []  # A restart loses the in-memory voice catalogue.
    voice_calls = []
    async def unavailable():
        voice_calls.append(1)
        raise TTSUnavailable("catalogue offline")
    engine.voices = unavailable
    for suffix in ("mp3", "words"):
        response = client.get(f"/api/v1/books/{book_id}/audio/{sentence_id}.{suffix}", params=options)
        assert response.status_code == 200
    assert voice_calls == []
    assert len(engine.calls) == 1


def test_stale_non_featured_voices_allow_cache_and_new_synthesis(client, epub2_bytes, engine):
    from lector.tts.base import TTSUnavailable, Voice
    ctx = client.app.state.ctx
    book_id = ctx.store.ingest(epub2_bytes).book.book_id
    ids = ctx.store.chapter_sentences(book_id, "c0")
    special = "fr-FR-HenriNeural"
    ctx.audio._voices = [Voice(voice_id=special, name="Henri", locale="fr-FR", gender="male", engine="fake")]
    ctx.audio._voices_at = time.monotonic()
    async def scenario():
        cached = await ctx.audio.tile(book_id, ids[0], special)
        ctx.audio._voices_at = float("-inf")
        calls = []
        async def unavailable():
            calls.append(1)
            raise TTSUnavailable("catalogue offline")
        engine.voices = unavailable
        assert (await ctx.audio.tile(book_id, ids[0], special)).audio == cached.audio
        assert calls == []  # A cache hit needs no catalogue refresh.
        assert await ctx.audio.tile(book_id, ids[1], special) is not None
        assert calls == [1]  # A failed refresh falls back to the stale allowlist.
        with pytest.raises(ValueError):
            await ctx.audio.tile(book_id, ids[0], "arbitrary-voice")
        assert calls == [1]  # Backoff also applies while using stale voices.
    asyncio.run(scenario())


def test_unknown_voice_cannot_reuse_a_cache_file_when_catalogue_is_down(client, epub2_bytes, engine):
    from lector.tts.base import TTSUnavailable
    from lector.tts.cache import cache_key
    ctx = client.app.state.ctx
    book_id = ctx.store.ingest(epub2_bytes).book.book_id
    sentence_id = ctx.store.chapter_sentences(book_id, "c0")[0]
    text = ctx.store.sentence_text(book_id, sentence_id)
    unknown = "untrusted-voice"
    result = asyncio.run(engine.synth(text, unknown))
    ctx.cache.store(cache_key(text.strip(), unknown, "+0%", engine.version), result)
    async def unavailable():
        raise TTSUnavailable("catalogue offline")
    engine.voices = unavailable
    response = client.get(
        f"/api/v1/books/{book_id}/audio/{sentence_id}.mp3", params={"voice_id": unknown},
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "TTS_UNAVAILABLE"


def test_voice_refresh_is_single_flight_and_failures_back_off(client, engine, monkeypatch):
    from lector.tts.base import TTSUnavailable
    ctx = client.app.state.ctx
    original = engine.voices
    calls = []
    now = [1000.0]
    from types import SimpleNamespace
    monkeypatch.setattr("lector.audio.time", SimpleNamespace(monotonic=lambda: now[0]))
    async def slow_voices():
        calls.append(1)
        await asyncio.sleep(0)
        return await original()
    engine.voices = slow_voices
    async def scenario():
        answers = await asyncio.gather(*[ctx.audio.voices() for _ in range(8)])
        assert all(answers)
        assert len(calls) == 1
        ctx.audio._voices = []
        async def fail():
            calls.append(1)
            raise TTSUnavailable("offline")
        engine.voices = fail
        for _ in range(3):
            with pytest.raises(TTSUnavailable):
                await ctx.audio.voices()
        assert len(calls) == 2
        now[0] += 6
        engine.voices = slow_voices
        assert await ctx.audio.voices()
        assert len(calls) == 3
    asyncio.run(scenario())


def test_synthesis_capacity_and_cancellation_release_resources(client, epub2_bytes, engine):
    from lector.audio import MAX_CONCURRENT_SYNTHESIS
    from lector.tts.base import TTSUnavailable
    ctx = client.app.state.ctx
    book_id = ctx.store.ingest(epub2_bytes).book.book_id
    sentence_id = ctx.store.chapter_sentences(book_id, "c0")[0]
    async def scenario():
        entered = asyncio.Event()
        release = asyncio.Event()
        active = 0
        original = engine.synth
        async def slow_synth(*args):
            nonlocal active
            active += 1
            if active == MAX_CONCURRENT_SYNTHESIS:
                entered.set()
            try:
                await release.wait()
                return await original(*args)
            finally:
                active -= 1
        engine.synth = slow_synth
        tasks = [asyncio.create_task(ctx.audio.tile(book_id, sentence_id, "zh-CN-YunxiNeural", f"+{i}%"))
                 for i in range(MAX_CONCURRENT_SYNTHESIS)]
        await asyncio.wait_for(entered.wait(), 1)
        with pytest.raises(TTSUnavailable, match="繁忙"):
            await ctx.audio.tile(book_id, sentence_id, "zh-CN-YunxiNeural", "+50%")
        waiter = asyncio.create_task(ctx.audio.tile(book_id, sentence_id, "zh-CN-YunxiNeural", "+0%"))
        await asyncio.sleep(0)
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        assert len(ctx.audio._locks) == MAX_CONCURRENT_SYNTHESIS
        tasks[0].cancel()
        with pytest.raises(asyncio.CancelledError):
            await tasks[0]
        release.set()
        await asyncio.gather(*tasks[1:])
        assert active == 0
        assert not ctx.audio._locks
    asyncio.run(scenario())


def test_default_cached_audio_works_without_voice_service(client, epub2_bytes, engine):
    ctx = client.app.state.ctx
    book_id = ctx.store.ingest(epub2_bytes).book.book_id
    sentence_id = ctx.store.chapter_sentences(book_id, "c0")[0]
    url = f"/api/v1/books/{book_id}/audio/{sentence_id}.mp3"
    assert client.get(url).status_code == 200
    ctx.audio._voices = []
    async def unavailable():
        raise AssertionError("default cached audio must not fetch the voice catalogue")
    engine.voices = unavailable
    assert client.get(url).status_code == 200


@pytest.mark.parametrize("endpoint", ["", "/audio", "/audio/warm"])
@pytest.mark.parametrize("token,provided,code", [
    ("secret:reader", "secret", "FORBIDDEN"),
    ("secret:admin", "wrong", "UNAUTHORIZED"),
    ("", None, "ADMIN_DISABLED"),
    (":admin", "", "ADMIN_DISABLED"),
])
def test_admin_permissions_survive_terminal_headers(settings, engine, epub2_bytes, endpoint, token, provided, code):
    client = make_client(settings, engine, peer="203.0.113.9", token=token)
    book_id = client.app.state.ctx.store.ingest(epub2_bytes).book.book_id
    headers = {"Host": "reader.example", "Origin": "http://reader.example", "X-Lector-Client": "terminal"}
    if provided is not None:
        headers["Authorization"] = f"Bearer {provided}"
    response = client.request(
        "POST" if endpoint.endswith("warm") else "DELETE",
        f"/api/v1/books/{book_id}{endpoint}", headers=headers,
        json={} if endpoint.endswith("warm") else None,
    )
    assert response.status_code in (401, 403)
    assert response.json()["error"]["code"] == code
    assert client.app.state.ctx.store.get_book(book_id) is not None


def test_malformed_bearer_reaches_auth_without_server_error(settings, engine):
    client = make_client(settings, engine, token="secret")
    response = client.delete(
        "/api/v1/books/b_deadbeef",
        headers={"authorization": b"Bearer \xff", "Origin": "http://localhost"},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_trusted_proxy_uses_verified_client_instead_of_leftmost_forwarded_ip(settings, engine, monkeypatch):
    from lector.api import deps
    from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
    client = make_client(settings, engine)
    app = client.app
    proxied = TestClient(
        ProxyHeadersMiddleware(app, trusted_hosts=["127.0.0.1"]),
        base_url="https://reader.example", client=("127.0.0.1", 50000),
    )
    monkeypatch.setattr(deps, "READ_LIMIT", 1)
    app.state.ctx.limiter.check("read", "203.0.113.9", 1)
    response = proxied.get(
        "/api/v1/books",
        headers={"X-Lector-Client": "terminal", "X-Forwarded-For": "198.51.100.8, 203.0.113.9"},
    )
    assert response.status_code == 429
