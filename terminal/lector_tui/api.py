"""A small synchronous client for the Lector API."""

from __future__ import annotations

import json
import ssl
from dataclasses import dataclass
from typing import BinaryIO
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

import certifi

from lector_tui.image_data import MAX_IMAGE_BYTES


def _read_image(response: BinaryIO) -> bytes:
    """Read at most the image budget plus one overflow-detection byte."""
    headers = getattr(response, "headers", {})
    try:
        expected = int(headers.get("Content-Length", ""))
    except (TypeError, ValueError):
        expected = -1
    if expected > MAX_IMAGE_BYTES:
        raise ValueError("图片下载超过 20 MiB 上限")
    data = bytearray()
    while chunk := response.read(min(64 * 1024, MAX_IMAGE_BYTES + 1 - len(data))):
        data.extend(chunk)
        if len(data) > MAX_IMAGE_BYTES:
            raise ValueError("图片下载超过 20 MiB 上限")
    if expected >= 0 and len(data) != expected:
        raise ValueError("图片下载不完整：响应长度不符")
    return bytes(data)


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
        # Keep the client identity explicit for request logs and compatibility
        # with the server's optional progress endpoints.
        headers = {"Accept": "application/json", "X-Lector-Client": "terminal"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _url(self, path: str, params: dict | None = None) -> str:
        url = f"{self.base_url.rstrip('/')}/api/v1{path}"
        if params:
            url = f"{url}?{urlencode(params)}"
        return url

    def _ssl_context(self) -> ssl.SSLContext:
        """Use the CA bundle shipped with the standalone binary."""
        return ssl.create_default_context(cafile=certifi.where())

    def request(self, path: str, params: dict | None = None):
        """Perform one read-only request and return the decoded payload."""
        headers = self._headers()
        request = Request(self._url(path, params), headers=headers, method="GET")
        try:
            with urlopen(request, timeout=30, context=self._ssl_context()) as response:
                payload = response.read()
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

    def audio_url(self, book_id: str, sentence_id: str, *, voice_id: str = "", rate: str = "+0%") -> str:
        params = {"voice_id": voice_id} if voice_id else {}
        if rate != "+0%":
            params["rate"] = rate
        return self._url(f"/books/{book_id}/audio/{quote(sentence_id)}.mp3", params)

    def get_words(self, book_id: str, sentence_id: str, *, voice_id: str = "", rate: str = "+0%") -> dict:
        params = {"voice_id": voice_id} if voice_id else {}
        if rate != "+0%":
            params["rate"] = rate
        return self.request(f"/books/{book_id}/audio/{quote(sentence_id)}.words", params=params)

    def fetch_media(self, book_id: str, path: str) -> bytes:
        """Download one image embedded in an EPUB."""
        media_path = quote(path.lstrip("/"), safe="/")
        request = Request(
            f"{self.base_url.rstrip('/')}/api/v1/books/{book_id}/media/{media_path}",
            headers=self._headers(),
        )
        with urlopen(request, timeout=60, context=self._ssl_context()) as response:
            return _read_image(response)

    def fetch_cover(self, book_id: str) -> bytes:
        """Download the shelf cover for one book."""
        request = Request(
            f"{self.base_url.rstrip('/')}/api/v1/books/{book_id}/cover",
            headers=self._headers(),
        )
        with urlopen(request, timeout=60, context=self._ssl_context()) as response:
            return _read_image(response)

    def download_audio(self, book_id: str, sentence_id: str, target: str, *, voice_id: str = "", rate: str = "+0%") -> str:
        """Download one sentence tile to a local file."""
        request = Request(self.audio_url(book_id, sentence_id, voice_id=voice_id, rate=rate), headers=self._headers())
        with urlopen(request, timeout=60, context=self._ssl_context()) as response:
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
