"""Progress, cross device hand-off and short codes."""

from __future__ import annotations

from test_api_books import upload


def setup(client, epub2_bytes: bytes) -> tuple[str, str]:
    book_id = upload(client, epub2_bytes).json()["book"]["book_id"]
    chapter = client.get(f"/api/v1/books/{book_id}/chapters/c0").json()["chapter"]
    sentence_id = chapter["blocks"][1]["sentences"][0]["id"]
    return book_id, sentence_id


def test_empty_progress_is_not_an_error(client, epub2_bytes: bytes):
    book_id, _ = setup(client, epub2_bytes)
    response = client.get(f"/api/v1/books/{book_id}/progress")
    assert response.status_code == 200
    payload = response.json()
    assert payload["cursor"] is None
    assert payload["percent"] == 0.0


def test_write_and_read_progress(client, epub2_bytes: bytes):
    book_id, sentence_id = setup(client, epub2_bytes)
    response = client.put(
        f"/api/v1/books/{book_id}/progress",
        json={
            "chapter_id": "c0",
            "sentence_id": sentence_id,
            "word_index": 2,
            "device_label": "MacBook Pro",
        },
        headers={"X-Lector-Client": "web"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["cursor"]["sentence_id"] == sentence_id
    assert payload["cursor"]["word_index"] == 2
    assert payload["updated_by"] == "web"
    assert payload["device_label"] == "MacBook Pro"
    assert 0.0 < payload["percent"] <= 1.0

    read = client.get(f"/api/v1/books/{book_id}/progress").json()
    assert read["cursor"] == payload["cursor"]


def test_progress_rejects_a_foreign_sentence(client, epub2_bytes: bytes):
    book_id, _ = setup(client, epub2_bytes)
    response = client.put(
        f"/api/v1/books/{book_id}/progress",
        json={"chapter_id": "c1", "sentence_id": "c0.b1.s0"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_repeated_write_keeps_the_timestamp(client, epub2_bytes: bytes):
    book_id, sentence_id = setup(client, epub2_bytes)
    body = {"chapter_id": "c0", "sentence_id": sentence_id}
    first = client.put(f"/api/v1/books/{book_id}/progress", json=body).json()
    second = client.put(f"/api/v1/books/{book_id}/progress", json=body).json()
    assert first["updated_at"] == second["updated_at"]


def test_terminal_can_take_over(client, epub2_bytes: bytes):
    book_id, sentence_id = setup(client, epub2_bytes)
    client.put(
        f"/api/v1/books/{book_id}/progress",
        json={"chapter_id": "c0", "sentence_id": sentence_id},
        headers={"X-Lector-Client": "web"},
    )
    payload = client.put(
        f"/api/v1/books/{book_id}/progress",
        json={"chapter_id": "c0", "sentence_id": sentence_id},
        headers={"X-Lector-Client": "terminal"},
    ).json()
    assert payload["updated_by"] == "terminal"


def test_short_code_round_trip(client, epub2_bytes: bytes):
    book_id, sentence_id = setup(client, epub2_bytes)
    created = client.post(
        "/api/v1/s",
        json={
            "book_id": book_id,
            "chapter_id": "c0",
            "sentence_id": sentence_id,
            "word_index": None,
        },
    )
    assert created.status_code == 200
    code = created.json()["code"]
    assert len(code) == 8
    assert created.json()["url"] == f"/s/{code}"

    resolved = client.get(f"/api/v1/s/{code}")
    assert resolved.status_code == 200
    assert resolved.json()["book_id"] == book_id
    assert resolved.json()["sentence_id"] == sentence_id


def test_short_code_is_stable(client, epub2_bytes: bytes):
    book_id, sentence_id = setup(client, epub2_bytes)
    body = {
        "book_id": book_id,
        "chapter_id": "c0",
        "sentence_id": sentence_id,
        "word_index": None,
    }
    first = client.post("/api/v1/s", json=body).json()["code"]
    second = client.post("/api/v1/s", json=body).json()["code"]
    assert first == second


def test_unknown_short_code_is_404(client):
    response = client.get("/api/v1/s/ZZZZZZZZ")
    assert response.status_code == 404
