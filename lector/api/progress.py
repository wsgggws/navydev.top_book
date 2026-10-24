"""Reading progress — the shared hand-off point between web and terminal."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from lector.api.deps import AppContext, get_context, require_auth, require_reader
from lector.api.errors import ApiError, validation_error
from lector.models import Progress, ProgressCursor, ProgressUpdate
from lector.store import utcnow

router = APIRouter(tags=["progress"])


def read_progress(ctx: AppContext, book_id: str) -> Progress:
    """The stored progress of a book; an empty progress is not an error."""
    row = ctx.store.db.query_one(
        "SELECT * FROM progress WHERE book_id = ?", (book_id,)
    )
    if row is None:
        return Progress(
            book_id=book_id,
            cursor=None,
            percent=0.0,
            updated_at=utcnow(),
            updated_by="api",
            device_label=None,
        )
    cursor = None
    if row["chapter_id"] and row["sentence_id"]:
        cursor = ProgressCursor(
            chapter_id=row["chapter_id"],
            sentence_id=row["sentence_id"],
            word_index=row["word_index"],
        )
    return Progress(
        book_id=book_id,
        cursor=cursor,
        percent=row["percent"],
        updated_at=row["updated_at"],
        updated_by=row["updated_by"],
        device_label=row["device_label"],
    )


@router.get("/books/{book_id}/progress", response_model=Progress)
async def get_progress(
    book_id: str,
    request: Request,
    _: None = Depends(require_auth),
) -> Progress:
    """Where the reader stopped."""
    ctx = get_context(request)
    if ctx.store.get_book(book_id) is None:
        raise ApiError(404, "NOT_FOUND", "书籍不存在", {"book_id": book_id})
    return read_progress(ctx, book_id)


@router.put("/books/{book_id}/progress", response_model=Progress)
async def write_progress(
    book_id: str,
    payload: ProgressUpdate,
    request: Request,
    _: None = Depends(require_reader),
) -> Progress:
    """Move the reading position.

    The later writer wins, but writing the same position again does not
    reorder the history — a scroll that fires a hundred writes must not
    out-pace another device that is genuinely further along.
    """
    ctx = get_context(request)
    if ctx.store.get_book(book_id) is None:
        raise ApiError(404, "NOT_FOUND", "书籍不存在", {"book_id": book_id})
    chapter_id = ctx.store.sentence_chapter(book_id, payload.sentence_id)
    if chapter_id is None or chapter_id != payload.chapter_id:
        raise validation_error(
            "句子不属于该章节",
            {
                "chapter_id": payload.chapter_id,
                "sentence_id": payload.sentence_id,
            },
        )
    percent = ctx.store.percent_for(book_id, payload.chapter_id, payload.sentence_id)
    now = utcnow()
    existing = ctx.store.db.query_one(
        "SELECT * FROM progress WHERE book_id = ?", (book_id,)
    )
    updated_at = now
    if existing is not None:
        same_place = (
            existing["chapter_id"] == payload.chapter_id
            and existing["sentence_id"] == payload.sentence_id
            and existing["word_index"] == payload.word_index
        )
        if same_place:
            updated_at = existing["updated_at"]
    with ctx.store.db.write() as conn:
        conn.execute(
            """
            INSERT INTO progress (book_id, chapter_id, sentence_id, word_index, percent,
                                   updated_at, updated_by, device_label)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(book_id) DO UPDATE SET
                chapter_id = excluded.chapter_id,
                sentence_id = excluded.sentence_id,
                word_index = excluded.word_index,
                percent = excluded.percent,
                updated_at = excluded.updated_at,
                updated_by = excluded.updated_by,
                device_label = excluded.device_label
            """,
            (
                book_id,
                payload.chapter_id,
                payload.sentence_id,
                payload.word_index,
                percent,
                updated_at,
                _source_of(request),
                payload.device_label,
            ),
        )
        conn.execute(
            "UPDATE books SET updated_at = ? WHERE book_id = ?", (utcnow(), book_id)
        )
    return read_progress(ctx, book_id)


def _source_of(request: Request) -> str:
    """Who is writing the progress."""
    header = request.headers.get("x-lector-client")
    if header in ("web", "terminal", "api"):
        return header
    return "api"
