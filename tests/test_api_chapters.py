"""Chapters, table of contents and the audio timeline."""

from __future__ import annotations

from test_api_books import upload


def first_book(client, epub2_bytes: bytes) -> str:
    return upload(client, epub2_bytes).json()["book"]["book_id"]


def test_toc_is_a_tree_of_nodes(client, epub2_bytes: bytes):
    book_id = first_book(client, epub2_bytes)
    response = client.get(f"/api/v1/books/{book_id}/toc")
    assert response.status_code == 200
    nodes = response.json()["toc"]
    assert len(nodes) == 2
    assert nodes[0]["title"] == "第一章"
    assert nodes[0]["chapter_id"] == "c0"
    assert nodes[0]["children"] == []
    # The node id is not the chapter id.
    assert nodes[0]["id"] != nodes[0]["chapter_id"]


def test_chapter_content(client, epub2_bytes: bytes):
    book_id = first_book(client, epub2_bytes)
    response = client.get(f"/api/v1/books/{book_id}/chapters/c0")
    assert response.status_code == 200
    payload = response.json()
    chapter = payload["chapter"]
    assert chapter["chapter_id"] == "c0"
    assert chapter["index"] == 0
    assert chapter["title"] == "第一章"
    assert chapter["sentence_count"] > 0
    block = chapter["blocks"][1]
    assert block["type"] == "p"
    assert block["id"] == "c0.b1"
    sentence = block["sentences"][0]
    assert sentence["id"] == "c0.b1.s0"
    assert sentence["char_start"] == 0
    assert sentence["char_end"] > 0
    assert payload["prev_chapter_id"] is None
    assert payload["next_chapter_id"] == "c1"


def test_chapter_links(client, epub2_bytes: bytes):
    book_id = first_book(client, epub2_bytes)
    last = client.get(f"/api/v1/books/{book_id}/chapters/c1").json()
    assert last["prev_chapter_id"] == "c0"
    assert last["next_chapter_id"] is None


def test_unknown_chapter_is_404(client, epub2_bytes: bytes):
    book_id = first_book(client, epub2_bytes)
    response = client.get(f"/api/v1/books/{book_id}/chapters/c99")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_timeline_is_empty_before_synthesis(client, epub2_bytes: bytes):
    book_id = first_book(client, epub2_bytes)
    response = client.get(f"/api/v1/books/{book_id}/chapters/c0/timeline")
    assert response.status_code == 200
    payload = response.json()
    assert payload["sentences"] == []
    assert payload["tts_state"] == "pending"
    assert payload["chapter_id"] == "c0"


def test_timeline_lists_synthesised_sentences(client, epub2_bytes: bytes):
    book_id = first_book(client, epub2_bytes)
    chapter = client.get(f"/api/v1/books/{book_id}/chapters/c0").json()["chapter"]
    sentence_id = chapter["blocks"][0]["sentences"][0]["id"]
    client.get(f"/api/v1/books/{book_id}/audio/{sentence_id}.mp3")
    payload = client.get(f"/api/v1/books/{book_id}/chapters/c0/timeline").json()
    assert payload["tts_state"] in ("pending", "partial")
    entry = next(item for item in payload["sentences"] if item["sentence_id"] == sentence_id)
    assert entry["start"] == 0.0
    assert entry["end"] > 0
    assert entry["audio_url"].endswith(f"{sentence_id}.mp3")
