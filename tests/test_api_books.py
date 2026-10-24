"""The book endpoints."""

from __future__ import annotations


def upload(client, data: bytes, **fields):
    return client.post(
        "/api/v1/books",
        files={"file": ("book.epub", data, "application/epub+zip")},
        data=fields,
    )


def test_health(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["parser_version"] >= 1
    assert payload["tts"]["engine"] == "fake"
    assert payload["books"] == 0


def test_upload_returns_201(client, epub2_bytes: bytes):
    response = upload(client, epub2_bytes)
    assert response.status_code == 201
    payload = response.json()
    assert payload["duplicate"] is False
    book = payload["book"]
    assert book["title"] == "测试书"
    assert book["author"] == "作者甲"
    assert book["chapter_count"] == 2
    assert book["sentence_count"] > 0
    assert book["book_id"].startswith("b_")
    assert book["cover_url"] is None


def test_upload_is_idempotent(client, epub2_bytes: bytes):
    first = upload(client, epub2_bytes)
    second = upload(client, epub2_bytes)
    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["duplicate"] is True
    assert second.json()["book"]["book_id"] == first.json()["book"]["book_id"]


def test_upload_can_override_metadata(client, epub2_bytes: bytes):
    response = upload(client, epub2_bytes, title="新名字", author="新作者")
    assert response.status_code == 201
    assert response.json()["book"]["title"] == "新名字"
    assert response.json()["book"]["author"] == "新作者"


def test_upload_rejects_non_zip(client):
    response = upload(client, b"not a zip")
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"


def test_upload_rejects_malicious_epub(client, malicious_bytes: bytes):
    response = upload(client, malicious_bytes)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "EPUB_INVALID"


def test_upload_rejects_oversized_file(client, settings):
    payload = b"PK\x03\x04" + b"0" * (settings.max_upload_bytes + 1024)
    response = upload(client, payload)
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"


def test_list_books(client, epub2_bytes: bytes):
    upload(client, epub2_bytes)
    upload(client, epub2_bytes)
    response = client.get("/api/v1/books")
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    assert len(payload) == 1


def test_get_book_returns_progress(client, epub2_bytes: bytes):
    book_id = upload(client, epub2_bytes).json()["book"]["book_id"]
    response = client.get(f"/api/v1/books/{book_id}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["book"]["book_id"] == book_id
    assert payload["progress"]["cursor"] is None
    assert payload["progress"]["percent"] == 0.0


def test_unknown_book_is_404(client):
    response = client.get("/api/v1/books/b_deadbeef")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_delete_book(client, epub2_bytes: bytes):
    book_id = upload(client, epub2_bytes).json()["book"]["book_id"]
    assert client.delete(f"/api/v1/books/{book_id}").status_code == 204
    assert client.get(f"/api/v1/books/{book_id}").status_code == 404
    assert client.delete(f"/api/v1/books/{book_id}").status_code == 404


def test_cover_is_404_without_cover(client, epub2_bytes: bytes):
    book_id = upload(client, epub2_bytes).json()["book"]["book_id"]
    assert client.get(f"/api/v1/books/{book_id}/cover").status_code == 404


def test_rate_limit_returns_429(client, epub2_bytes: bytes):
    for _ in range(10):
        upload(client, epub2_bytes)
    response = upload(client, epub2_bytes)
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "RATE_LIMITED"
    assert "Retry-After" in response.headers


def test_reads_are_rate_limited(client):
    """The read budget of the contract is enforced."""
    for _ in range(600):
        response = client.get("/api/v1/books")
        assert response.status_code == 200
    response = client.get("/api/v1/books")
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "RATE_LIMITED"


def test_token_is_required_when_configured(tmp_path, epub2_bytes: bytes):
    """With a token configured every endpoint but health asks for it."""
    import os

    from fastapi.testclient import TestClient

    from lector.config import load_settings
    from lector.web import create_app

    os.environ["LECTOR_TOKEN"] = "s3cret"
    try:
        settings = load_settings(tmp_path / "data")
        client = TestClient(create_app(settings))
        assert client.get("/api/v1/health").status_code == 200
        assert client.get("/api/v1/books").status_code == 401
        assert client.get("/api/v1/books", headers={"Authorization": "Bearer wrong"}).status_code == 401
        ok = client.get("/api/v1/books", headers={"Authorization": "Bearer s3cret"})
        assert ok.status_code == 200
    finally:
        os.environ.pop("LECTOR_TOKEN", None)


def test_media_endpoint_serves_images(client, epub2_bytes: bytes):
    """Images inside the book are served from the archive."""
    from tests.factories import build_epub2

    data = build_epub2(
        chapters=[("图", '<div><img src="images/f1.jpg" alt="图"/></div>')]
    )
    book_id = upload(client, data).json()["book"]["book_id"]
    chapter = client.get(f"/api/v1/books/{book_id}/chapters/c0").json()["chapter"]
    image = next(block for block in chapter["blocks"] if block["type"] == "img")
    response = client.get(f"/api/v1/books/{book_id}/media/{image['src']}")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.content.startswith(b"\xff\xd8")
    assert client.get(f"/api/v1/books/{book_id}/media/../../etc/passwd").status_code in (404, 400)
