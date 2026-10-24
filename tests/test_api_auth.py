"""令牌与权限分级。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from lector.config import load_settings
from lector.web import create_app


@pytest.fixture
def client_for(tmp_path, monkeypatch):
    """A client for a server configured with the given token."""

    def make(token: str) -> TestClient:
        # monkeypatch 会一直保留到用例结束，服务端读到的就是这个令牌。
        monkeypatch.setenv("LECTOR_TOKEN", token)
        # 同一个数据目录：变的只是令牌，不是书架。
        settings = load_settings(tmp_path / "data")
        return TestClient(create_app(settings))

    return make


def test_health_needs_no_token(client_for):
    client = client_for("secret")
    assert client.get("/api/v1/health").status_code == 200


def test_reading_needs_the_token(client_for):
    client = client_for("secret")
    assert client.get("/api/v1/books").status_code == 401
    assert client.get("/api/v1/books", headers={"Authorization": "Bearer wrong"}).status_code == 401
    ok = client.get("/api/v1/books", headers={"Authorization": "Bearer secret"})
    assert ok.status_code == 200


def test_a_reader_token_may_not_upload(client_for, epub2_bytes: bytes):
    """终端端只读：reader 令牌不能往书架里加书。"""
    client = client_for("secret:reader")
    headers = {"Authorization": "Bearer secret"}
    response = client.post(
        "/api/v1/books",
        files={"file": ("book.epub", epub2_bytes, "application/epub+zip")},
        headers=headers,
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_a_reader_token_may_not_delete(client_for, epub2_bytes: bytes):
    admin = client_for("secret:admin")
    created = admin.post(
        "/api/v1/books",
        files={"file": ("book.epub", epub2_bytes, "application/epub+zip")},
        headers={"Authorization": "Bearer secret"},
    )
    book_id = created.json()["book"]["book_id"]

    client = client_for("secret:reader")
    response = client.delete(
        f"/api/v1/books/{book_id}", headers={"Authorization": "Bearer secret"}
    )
    assert response.status_code == 403


def test_a_reader_token_may_record_its_progress(client_for, epub2_bytes: bytes):
    """读自己的位置是允许的 —— 跨端接力靠它。"""
    admin = client_for("secret:admin")
    created = admin.post(
        "/api/v1/books",
        files={"file": ("book.epub", epub2_bytes, "application/epub+zip")},
        headers={"Authorization": "Bearer secret"},
    )
    book_id = created.json()["book"]["book_id"]
    chapter = admin.get(
        f"/api/v1/books/{book_id}/chapters/c0",
        headers={"Authorization": "Bearer secret"},
    ).json()["chapter"]
    sentence_id = chapter["blocks"][1]["sentences"][0]["id"]

    reader = client_for("secret:reader")
    response = reader.put(
        f"/api/v1/books/{book_id}/progress",
        json={"chapter_id": "c0", "sentence_id": sentence_id},
        headers={"Authorization": "Bearer secret"},
    )
    assert response.status_code == 200
    assert response.json()["cursor"]["sentence_id"] == sentence_id


def test_meta_tells_the_client_its_scope(client_for):
    client = client_for("secret:reader")
    payload = client.get(
        "/api/v1/meta", headers={"Authorization": "Bearer secret"}
    ).json()
    assert payload["scope"] == "reader"

    admin = client_for("secret")
    payload = admin.get(
        "/api/v1/meta", headers={"Authorization": "Bearer secret"}
    ).json()
    assert payload["scope"] == "admin"
