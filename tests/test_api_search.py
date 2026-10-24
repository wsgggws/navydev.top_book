"""Search inside a book."""

from __future__ import annotations

from test_api_books import upload


def setup(client, epub2_bytes: bytes) -> str:
    return upload(client, epub2_bytes).json()["book"]["book_id"]


def test_search_finds_a_sentence(client, epub2_bytes: bytes):
    book_id = setup(client, epub2_bytes)
    response = client.get(f"/api/v1/books/{book_id}/search", params={"q": "玫瑰"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["query"] == "玫瑰"
    assert payload["total"] >= 1
    result = payload["results"][0]
    assert "<em>玫瑰</em>" in result["snippet"]
    assert result["chapter_id"] == "c0"
    assert result["sentence_id"].startswith("c0.")


def test_search_results_keep_the_book_order(client, epub2_bytes: bytes):
    book_id = setup(client, epub2_bytes)
    payload = client.get(f"/api/v1/books/{book_id}/search", params={"q": "e"}).json()
    ids = [result["sentence_id"] for result in payload["results"]]
    chapters = [result["chapter_id"] for result in payload["results"]]
    assert chapters == sorted(chapters)


def test_empty_query_is_400(client, epub2_bytes: bytes):
    book_id = setup(client, epub2_bytes)
    response = client.get(f"/api/v1/books/{book_id}/search", params={"q": "  "})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "BAD_REQUEST"


def test_search_in_unknown_book_is_404(client):
    assert client.get("/api/v1/books/b_nope/search", params={"q": "x"}).status_code == 404
