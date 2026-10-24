"""Audio tiles, the word boundaries and the cache."""

from __future__ import annotations

from test_api_books import upload


def setup(client, epub2_bytes: bytes) -> tuple[str, str]:
    book_id = upload(client, epub2_bytes).json()["book"]["book_id"]
    chapter = client.get(f"/api/v1/books/{book_id}/chapters/c0").json()["chapter"]
    sentence_id = chapter["blocks"][1]["sentences"][0]["id"]
    return book_id, sentence_id


def test_audio_is_synthesised_on_demand(client, epub2_bytes: bytes, engine):
    book_id, sentence_id = setup(client, epub2_bytes)
    response = client.get(f"/api/v1/books/{book_id}/audio/{sentence_id}.mp3")
    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mpeg"
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert int(response.headers["content-length"]) == len(response.content)
    assert engine.calls
    assert engine.calls[-1][2] == "+0%"


def test_audio_is_cached(client, epub2_bytes: bytes, engine):
    book_id, sentence_id = setup(client, epub2_bytes)
    client.get(f"/api/v1/books/{book_id}/audio/{sentence_id}.mp3")
    calls_after_first = len(engine.calls)
    client.get(f"/api/v1/books/{book_id}/audio/{sentence_id}.mp3")
    assert len(engine.calls) == calls_after_first


def test_english_uses_a_slightly_slower_baseline(client, engine):
    """English 1x is slower than Chinese 1x without changing the UI rate."""
    from tests.factories import build_epub2

    data = build_epub2(language="en-US")
    book_id = upload(client, data).json()["book"]["book_id"]
    chapter = client.get(f"/api/v1/books/{book_id}/chapters/c0").json()["chapter"]
    sentence_id = chapter["blocks"][1]["sentences"][0]["id"]

    response = client.get(f"/api/v1/books/{book_id}/audio/{sentence_id}.mp3")
    assert response.status_code == 200
    assert engine.calls[-1][2] == "-8%"


def test_words_expose_granularity(client, epub2_bytes: bytes):
    book_id, sentence_id = setup(client, epub2_bytes)
    response = client.get(f"/api/v1/books/{book_id}/audio/{sentence_id}.words")
    assert response.status_code == 200
    payload = response.json()
    assert payload["sentence_id"] == sentence_id
    assert payload["granularity"] == "word"
    assert payload["duration"] > 0
    assert payload["words"]
    for word in payload["words"]:
        assert word["start"] <= word["end"]
        assert word["text"]


def test_unknown_sentence_audio_is_404(client, epub2_bytes: bytes):
    book_id, _ = setup(client, epub2_bytes)
    response = client.get(f"/api/v1/books/{book_id}/audio/c0.b0.s999.mp3")
    assert response.status_code == 404


def test_warm_reports_counts(client, epub2_bytes: bytes):
    book_id, _ = setup(client, epub2_bytes)
    response = client.post(
        f"/api/v1/books/{book_id}/audio/warm", json={"chapter_id": "c0"}
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["queued"] > 0
    assert payload["ready"] == payload["queued"]
    assert payload["failed"] == 0
    assert payload["state"] in ("partial", "ready")


def test_clear_audio(client, epub2_bytes: bytes):
    book_id, _ = setup(client, epub2_bytes)
    client.post(f"/api/v1/books/{book_id}/audio/warm", json={"chapter_id": "c0"})
    assert client.delete(f"/api/v1/books/{book_id}/audio").status_code == 204
    payload = client.get(f"/api/v1/books/{book_id}/chapters/c0/timeline").json()
    assert payload["sentences"] == []


def test_engine_failure_returns_503(settings, epub2_bytes: bytes):
    from fastapi.testclient import TestClient

    from lector.web import create_app
    from tests.conftest import FailingEngine

    app = create_app(settings)
    failing = FailingEngine()
    app.state.ctx.engine = failing
    app.state.ctx.audio.engine = failing
    client = TestClient(app)
    book_id = upload(client, epub2_bytes).json()["book"]["book_id"]
    chapter = client.get(f"/api/v1/books/{book_id}/chapters/c0").json()["chapter"]
    sentence_id = chapter["blocks"][1]["sentences"][0]["id"]
    response = client.get(f"/api/v1/books/{book_id}/audio/{sentence_id}.mp3")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "TTS_UNAVAILABLE"


def test_health_is_degraded_without_an_engine(settings):
    from fastapi.testclient import TestClient

    from lector.web import create_app
    from tests.conftest import FailingEngine

    app = create_app(settings)
    failing = FailingEngine()
    app.state.ctx.engine = failing
    app.state.ctx.audio.engine = failing
    client = TestClient(app)
    payload = client.get("/api/v1/health").json()
    assert payload["status"] == "degraded"
    assert payload["tts"]["available"] is False


def test_voices_endpoint(client):
    response = client.get("/api/v1/tts/voices")
    assert response.status_code == 200
    payload = response.json()
    assert payload["engine"] == "fake"
    assert payload["voices"]
    assert payload["voices"][0]["voice_id"].startswith("zh-CN")
