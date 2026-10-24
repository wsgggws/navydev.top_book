"""A small synchronous client for the Lector API."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


class ApiError(Exception):
    """The server refused the request."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message or code)
        self.status = status
        self.code = code
        self.message = message


@dataclass
class ApiClient:
    """Talks to the Lector HTTP API."""

    base_url: str = "http://127.0.0.1:8000"
    token: str = ""

    def _headers(self) -> dict[str, str]:
        # The server records who moved the cursor, so the two ends can tell
        # each other apart.
        headers = {"Accept": "application/json", "X-Lector-Client": "terminal"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _url(self, path: str, params: dict | None = None) -> str:
        url = f"{self.base_url.rstrip('/')}/api/v1{path}"
        if params:
            url = f"{url}?{urlencode(params)}"
        return url

    def request(self, path: str, params: dict | None = None, method: str = "GET",
                body: dict | None = None, raw: bool = False):
        """Perform one request and return the decoded payload."""
        headers = self._headers()
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(self._url(path, params), data=data, headers=headers, method=method)
        try:
            with urlopen(request, timeout=30) as response:
                payload = response.read()
                if raw:
                    return payload
                if not payload:
                    return None
                return json.loads(payload.decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read()
            code, message = "INTERNAL_ERROR", exc.reason
            try:
                parsed = json.loads(detail.decode("utf-8"))
                code = parsed.get("error", {}).get("code", code)
                message = parsed.get("error", {}).get("message", message)
            except (ValueError, UnicodeDecodeError):
                pass
            raise ApiError(exc.code, code, str(message)) from exc
        except URLError as exc:
            raise ApiError(0, "CONNECTION_ERROR", f"无法连接服务器：{exc.reason}") from exc

    # -- endpoints -------------------------------------------------------
    def health(self) -> dict:
        return self.request("/health")

    def voices(self) -> dict:
        return self.request("/tts/voices")

    def list_books(self) -> list[dict]:
        return self.request("/books")

    def get_book(self, book_id: str) -> dict:
        return self.request(f"/books/{book_id}")

    def get_toc(self, book_id: str) -> list[dict]:
        return self.request(f"/books/{book_id}/toc").get("toc", [])

    def get_chapter(self, book_id: str, chapter_id: str) -> dict:
        return self.request(f"/books/{book_id}/chapters/{chapter_id}")

    def get_timeline(self, book_id: str, chapter_id: str) -> dict:
        return self.request(f"/books/{book_id}/chapters/{chapter_id}/timeline")

    def audio_url(self, book_id: str, sentence_id: str) -> str:
        return f"{self.base_url.rstrip('/')}/api/v1/books/{book_id}/audio/{sentence_id}.mp3"

    def get_words(self, book_id: str, sentence_id: str) -> dict:
        return self.request(f"/books/{book_id}/audio/{quote(sentence_id)}.words")

    def download_audio(self, book_id: str, sentence_id: str, target: str) -> str:
        """Download one sentence tile to a local file."""
        request = Request(self.audio_url(book_id, sentence_id), headers=self._headers())
        with urlopen(request, timeout=60) as response:
            data = response.read()
        with open(target, "wb") as handle:
            handle.write(data)
        return target

    def percent(self, book_id: str, chapter_id: str, sentence_id: str) -> float:
        """把游标换算成全书百分比（服务端不记任何东西）。"""
        payload = self.request(
            f"/books/{book_id}/percent",
            params={"chapter_id": chapter_id, "sentence_id": sentence_id},
        )
        return float(payload.get("percent", 0.0))

    def search(self, book_id: str, query: str, limit: int = 20) -> dict:
        return self.request(f"/books/{book_id}/search", params={"q": query, "limit": limit})
