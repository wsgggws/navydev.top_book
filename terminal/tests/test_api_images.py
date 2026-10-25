"""Cover/media downloads are bounded even without a trustworthy length."""

from __future__ import annotations

from io import BytesIO

from PIL import Image
import pytest

from lector_tui.api import ApiClient


LIMIT = 20 * 1024 * 1024


class Response(BytesIO):
    def __init__(self, data: bytes, headers: dict[str, str] | None = None) -> None:
        super().__init__(data)
        self.headers = headers or {}
        self.read_sizes: list[int] = []

    def read(self, size: int = -1) -> bytes:
        self.read_sizes.append(size)
        assert 0 < size <= 64 * 1024, "network reads must use bounded chunks"
        return super().read(size)


def download(client: ApiClient, endpoint: str) -> bytes:
    if endpoint == "cover":
        return client.fetch_cover("book-1")
    return client.fetch_media("book-1", "/OEBPS/a b.png")


@pytest.mark.parametrize("endpoint", ["cover", "media"])
def test_images_use_bounded_reads_and_preserve_request_headers(monkeypatch, endpoint):
    buffer = BytesIO()
    Image.new("RGB", (8, 8), "red").save(buffer, format="PNG")
    data = buffer.getvalue()
    response = Response(data)
    requests = []

    def urlopen(request, **kwargs):
        requests.append(request)
        return response

    monkeypatch.setattr("lector_tui.api.urlopen", urlopen)
    assert download(ApiClient("https://example.test/ebook/", "secret"), endpoint) == data
    assert response.closed
    request = requests[0]
    assert request.get_header("X-lector-client") == "terminal"
    assert request.get_header("Authorization") == "Bearer secret"
    suffix = "cover" if endpoint == "cover" else "media/OEBPS/a%20b.png"
    assert request.full_url == f"https://example.test/ebook/api/v1/books/book-1/{suffix}"


@pytest.mark.parametrize("endpoint", ["cover", "media"])
def test_declared_oversized_images_are_rejected_before_reading(monkeypatch, endpoint):
    response = Response(b"", {"Content-Length": str(LIMIT + 1)})
    monkeypatch.setattr("lector_tui.api.urlopen", lambda *args, **kwargs: response)
    with pytest.raises(ValueError, match="20 MiB"):
        download(ApiClient(), endpoint)
    assert not response.read_sizes
    assert response.closed


@pytest.mark.parametrize("endpoint", ["cover", "media"])
@pytest.mark.parametrize("length", [None, "1", "invalid", "-1"])
def test_actual_image_size_is_limited_regardless_of_length_header(monkeypatch, endpoint, length):
    headers = {} if length is None else {"Content-Length": length}
    response = Response(b"x" * (LIMIT + 1), headers)
    monkeypatch.setattr("lector_tui.api.urlopen", lambda *args, **kwargs: response)
    with pytest.raises(ValueError, match="20 MiB"):
        download(ApiClient(), endpoint)
    assert sum(response.read_sizes) == LIMIT + 1
    assert response.closed


@pytest.mark.parametrize("endpoint", ["cover", "media"])
def test_exactly_twenty_mib_is_accepted(monkeypatch, endpoint):
    data = b"x" * LIMIT
    response = Response(data, {"Content-Length": str(LIMIT)})
    monkeypatch.setattr("lector_tui.api.urlopen", lambda *args, **kwargs: response)
    assert download(ApiClient(), endpoint) == data
    assert response.closed


@pytest.mark.parametrize("endpoint", ["cover", "media"])
def test_truncated_download_is_rejected_and_closed(monkeypatch, endpoint):
    response = Response(b"short", {"Content-Length": "100"})
    monkeypatch.setattr("lector_tui.api.urlopen", lambda *args, **kwargs: response)
    with pytest.raises(ValueError, match="不完整"):
        download(ApiClient(), endpoint)
    assert response.closed
