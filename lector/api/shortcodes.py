"""Short codes for sharing a position."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from lector.api.deps import get_context, public_read
from lector.api.errors import ApiError
from lector.models import ShortCodeRequest, ShortCodeResponse
from lector.positions import generate_short_code, normalize_short_code
from lector.store import utcnow

router = APIRouter(tags=["shortcodes"])

#: How many attempts to make before giving up on a free code.
CODE_ATTEMPTS = 8


@router.post("/s", response_model=ShortCodeResponse)
async def create_short_code(
    payload: ShortCodeRequest,
    request: Request,
    _: None = Depends(public_read),
) -> ShortCodeResponse:
    """Share a position.  The same position always gets the same code."""
    ctx = get_context(request)
    if ctx.store.get_book(payload.book_id) is None:
        raise ApiError(404, "NOT_FOUND", "书籍不存在", {"book_id": payload.book_id})
    existing = ctx.store.db.query_one(
        """
        SELECT code FROM short_codes
        WHERE book_id = ? AND chapter_id = ? AND sentence_id = ?
          AND (word_index IS ? OR word_index = ?)
        """,
        (
            payload.book_id,
            payload.chapter_id,
            payload.sentence_id,
            payload.word_index,
            payload.word_index,
        ),
    )
    base = get_context(request).settings.base_path
    if existing is not None:
        code = existing["code"]
        return ShortCodeResponse(code=code, url=f"{base}/s/{code}")
    for _ in range(CODE_ATTEMPTS):
        code = generate_short_code()
        taken = ctx.store.db.query_one(
            "SELECT 1 FROM short_codes WHERE code = ?", (code,)
        )
        if taken is not None:
            continue
        with ctx.store.db.write() as conn:
            conn.execute(
                """
                INSERT INTO short_codes (code, book_id, chapter_id, sentence_id, word_index,
                                         created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    code,
                    payload.book_id,
                    payload.chapter_id,
                    payload.sentence_id,
                    payload.word_index,
                    utcnow(),
                ),
            )
        return ShortCodeResponse(code=code, url=f"{base}/s/{code}")
    raise ApiError(500, "INTERNAL_ERROR", "短码生成失败，请重试")


@router.get("/s/{code}")
async def resolve_short_code(
    code: str,
    request: Request,
    _: None = Depends(public_read),
) -> dict:
    """Resolve a share code back into a cursor."""
    ctx = get_context(request)
    normalized = normalize_short_code(code)
    row = ctx.store.db.query_one(
        "SELECT * FROM short_codes WHERE code = ?", (normalized,)
    )
    if row is None:
        raise ApiError(404, "NOT_FOUND", "短码不存在或已过期", {"code": code})
    return {
        "book_id": row["book_id"],
        "chapter_id": row["chapter_id"],
        "sentence_id": row["sentence_id"],
        "word_index": row["word_index"],
    }
