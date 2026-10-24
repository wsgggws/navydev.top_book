"""Upload, list, read and delete books."""

from __future__ import annotations

import posixpath
import time
import zipfile

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool

from lector.api.deps import (
    AppContext,
    client_address,
    get_context,
    public_read,
    require_admin,
)
from lector.api.errors import ApiError, epub_invalid
from lector.epub.errors import EpubError, EpubNotAZipError
from lector.models import Book, BookDetailResponse, UploadResponse

router = APIRouter(tags=["books"])


def require_book(ctx: AppContext, book_id: str):
    """Return the book or raise a 404."""
    book = ctx.store.get_book(book_id)
    if book is None:
        raise ApiError(404, "NOT_FOUND", "书籍不存在", {"book_id": book_id})
    return book

#: The contract allows eight seconds of parsing before the upload is refused.
PARSE_TIMEOUT = 10.0

_IMAGE_TYPES = {
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"GIF87a": "image/gif",
    b"GIF89a": "image/gif",
    b"RIFF": "image/webp",
}


@router.post("/books", response_model=UploadResponse)
async def upload_book(
    request: Request,
    response: Response,
    file: UploadFile = File(...),
    title: str | None = Form(None),
    author: str | None = Form(None),
    voice_id: str | None = Form(None),
    _: None = Depends(require_admin),
) -> UploadResponse:
    """Upload an EPUB.  Uploading the same file twice returns the first book."""
    ctx = get_context(request)
    ctx.limiter.check("upload", client_address(request), 10)

    data = await _read_upload(file, ctx.settings.max_upload_bytes)
    started = time.monotonic()
    try:
        result = await run_in_threadpool(ctx.store.ingest, data, title, author, voice_id)
    except EpubNotAZipError as exc:
        raise ApiError(415, "UNSUPPORTED_MEDIA_TYPE", exc.message, exc.detail) from exc
    except EpubError as exc:
        raise epub_invalid(exc.message, exc.detail) from exc
    elapsed = time.monotonic() - started
    if elapsed > PARSE_TIMEOUT:
        raise epub_invalid(
            "EPUB 结构不完整：解析超时", {"seconds": round(elapsed, 2)}
        )
    response.status_code = 200 if result.duplicate else 201
    return UploadResponse(book=result.book, duplicate=result.duplicate)


async def _read_upload(file: UploadFile, limit: int) -> bytes:
    """Read the upload, refusing anything above the size limit."""
    buffer = bytearray()
    while True:
        chunk = await file.read(1 << 16)
        if not chunk:
            break
        buffer.extend(chunk)
        if len(buffer) > limit:
            raise ApiError(
                413,
                "PAYLOAD_TOO_LARGE",
                "文件超过 50MB 上限",
                {"limit_bytes": limit},
            )
    if not buffer:
        raise epub_invalid("EPUB 结构不完整：文件为空")
    return bytes(buffer)


@router.get("/books", response_model=list[Book])
async def list_books(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _: None = Depends(public_read),
) -> list[Book]:
    """The library, newest first."""
    ctx = get_context(request)
    return ctx.store.list_books(limit=limit, offset=offset)


@router.get("/books/{book_id}", response_model=BookDetailResponse)
async def get_book(
    book_id: str,
    request: Request,
    _: None = Depends(public_read),
) -> BookDetailResponse:
    """One book together with its reading progress."""
    ctx = get_context(request)
    book = ctx.store.get_book(book_id)
    if book is None:
        raise ApiError(404, "NOT_FOUND", "书籍不存在", {"book_id": book_id})
    from lector.api.progress import read_progress

    progress = read_progress(ctx, book_id)
    return BookDetailResponse(book=book, progress=progress)


@router.delete("/books/{book_id}", status_code=204)
async def delete_book(
    book_id: str,
    request: Request,
    _: None = Depends(require_admin),
) -> Response:
    """Delete a book with its parsed content and audio."""
    ctx = get_context(request)
    if not ctx.store.delete(book_id):
        raise ApiError(404, "NOT_FOUND", "书籍不存在", {"book_id": book_id})
    return Response(status_code=204)


@router.get("/books/{book_id}/cover")
async def get_cover(
    book_id: str,
    request: Request,
    _: None = Depends(public_read),
) -> Response:
    """The cover image, if the book has one."""
    ctx = get_context(request)
    path = ctx.store.cover_path(book_id)
    if path is None:
        raise ApiError(404, "NOT_FOUND", "该书没有封面", {"book_id": book_id})
    media_type = _image_type(path.read_bytes()[:16]) or "image/jpeg"
    return FileResponse(
        path,
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )


def _image_type(head: bytes) -> str | None:
    """Detect the image type from its magic bytes."""
    for signature, media_type in _IMAGE_TYPES.items():
        if head.startswith(signature):
            return media_type
    return None


@router.get("/books/{book_id}/media/{path:path}")
async def get_media(
    book_id: str,
    path: str,
    request: Request,
    _: None = Depends(public_read),
) -> Response:
    """An image from inside the EPUB.

    The path is the EPUB-internal one the chapter payload exposes.  Only
    members of the archive are served, and the lookup never escapes it.
    """
    ctx = get_context(request)
    require_book(ctx, book_id)
    normalized = posixpath.normpath(path)
    if normalized.startswith("..") or normalized.startswith("/"):
        raise ApiError(404, "NOT_FOUND", "资源不存在", {"path": path})
    source = ctx.store.source_path(book_id)
    if not source.exists():
        raise ApiError(404, "NOT_FOUND", "书籍不存在", {"book_id": book_id})
    try:
        with zipfile.ZipFile(source) as zf:
            data = zf.read(normalized)
    except (KeyError, OSError, zipfile.BadZipFile) as exc:
        raise ApiError(404, "NOT_FOUND", "资源不存在", {"path": path}) from exc
    media_type = _image_type(data[:16]) or "application/octet-stream"
    return Response(
        content=data,
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )
