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


def test_token_protects_admin_writes_but_not_reading(tmp_path, epub2_bytes: bytes):
    """Public browsing stays open; uploads still require the admin token."""
    import os

    from fastapi.testclient import TestClient

    from lector.config import load_settings
    from lector.web import create_app

    os.environ["LECTOR_TOKEN"] = "s3cret"
    try:
        settings = load_settings(tmp_path / "data")
        client = TestClient(create_app(settings))
        assert client.get("/api/v1/health").status_code == 200
        assert client.get("/api/v1/books").status_code == 200
        assert client.post(
            "/api/v1/books",
            files={"file": ("book.epub", epub2_bytes, "application/epub+zip")},
        ).status_code == 401
        assert client.post(
            "/api/v1/books",
            files={"file": ("book.epub", epub2_bytes, "application/epub+zip")},
            headers={"Authorization": "Bearer wrong"},
        ).status_code == 401
        created = client.post(
            "/api/v1/books",
            files={"file": ("book.epub", epub2_bytes, "application/epub+zip")},
            headers={"Authorization": "Bearer s3cret"},
        )
        assert created.status_code == 201
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


def test_the_shelf_shows_each_books_own_progress(client, epub2_bytes: bytes):
    """每本书各记各的进度。"""
    from factories import build_epub2

    other = build_epub2(title="另一本", author="乙")
    first_id = upload(client, epub2_bytes).json()["book"]["book_id"]
    second_id = upload(client, other).json()["book"]["book_id"]

    chapter = client.get(f"/api/v1/books/{first_id}/chapters/c0").json()["chapter"]
    sentence_id = chapter["blocks"][1]["sentences"][0]["id"]
    client.put(
        f"/api/v1/books/{first_id}/progress",
        json={"chapter_id": "c0", "sentence_id": sentence_id},
    )

    books = {book["book_id"]: book for book in client.get("/api/v1/books").json()}
    assert books[first_id]["progress"] > 0
    assert books[second_id]["progress"] == 0


def test_the_app_can_live_under_a_path(tmp_path, epub2_bytes: bytes):
    """挂在 /book 下时，接口、静态资源与短码都跟着走。"""
    from fastapi.testclient import TestClient

    from lector.config import load_settings
    from lector.web import create_app

    settings = load_settings(tmp_path / "data")
    settings = settings.__class__(**{**settings.__dict__, "base_path": "/book"})
    client = TestClient(create_app(settings))
    book_id = client.post(
        "/book/api/v1/books",
        files={"file": ("book.epub", epub2_bytes, "application/epub+zip")},
    ).json()["book"]["book_id"]

    # 接口在 /book/api/v1
    assert client.get("/book/api/v1/health").status_code == 200
    assert client.get("/book/api/v1/books").status_code == 200
    # 页面在 /book 与 /book/，并把基路径告诉前端
    page = client.get("/book")
    assert page.status_code == 200
    assert '<base href="/book/">' in page.text
    assert 'window.lectorBase="/book"' in page.text
    assert "styles/tokens.css?v=" in page.text
    assert "js/app.js?v=" in page.text
    assert '<script type="importmap">' in page.text
    assert '"/book/js/views/library.js":"/book/js/views/library.js?v=' in page.text
    assert page.headers["cache-control"] == "no-cache"

    page = client.get("/book/")
    assert page.status_code == 200
    assert '<base href="/book/">' in page.text
    assert 'window.lectorBase="/book"' in page.text
    # 封面地址也带前缀（测试书没有封面，有的话必须是带前缀的）
    books = client.get("/book/api/v1/books").json()
    if books[0]["cover_url"]:
        assert books[0]["cover_url"].startswith("/book/api/v1/")

    # 短码链接带前缀
    chapter = client.get(f"/book/api/v1/books/{book_id}/chapters/c0").json()["chapter"]
    sentence_id = chapter["blocks"][1]["sentences"][0]["id"]
    created = client.post(
        "/book/api/v1/s",
        json={
            "book_id": book_id,
            "chapter_id": "c0",
            "sentence_id": sentence_id,
            "word_index": None,
        },
    ).json()
    assert created["url"].startswith("/book/s/")


def test_repository_books_are_imported_and_public(tmp_path, epub2_bytes: bytes):
    """Books committed under books/ appear without upload or a token."""
    from fastapi.testclient import TestClient

    from lector.config import load_settings
    from lector.web import create_app, sync_seed_books

    library = tmp_path / "library"
    library.mkdir()
    (library / "seed.epub").write_bytes(epub2_bytes)

    settings = load_settings(tmp_path / "data")
    settings = settings.__class__(
        **{**settings.__dict__, "seed_books_dir": library}
    )
    app = create_app(settings)
    sync_seed_books(app.state.ctx.store, settings.seed_books_dir)
    client = TestClient(app)

    books = client.get("/api/v1/books")
    assert books.status_code == 200
    assert len(books.json()) == 1
    assert "btn-import" not in client.get("/").text
