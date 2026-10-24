"""Full text search inside one book."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from lector.api.deps import get_context, public_read
from lector.api.errors import ApiError, bad_request
from lector.models import SearchResponse, SearchResult

router = APIRouter(tags=["search"])

#: Characters of context kept on each side of a hit.
CONTEXT_LENGTH = 40

#: The longest snippet the response may contain.
SNIPPET_LENGTH = 200


@router.get("/books/{book_id}/search", response_model=SearchResponse)
async def search(
    book_id: str,
    request: Request,
    q: str = Query("", min_length=0),
    limit: int = Query(50, ge=1, le=200),
    _: None = Depends(public_read),
) -> SearchResponse:
    """Find sentences that contain the query."""
    ctx = get_context(request)
    if ctx.store.get_book(book_id) is None:
        raise ApiError(404, "NOT_FOUND", "书籍不存在", {"book_id": book_id})
    query = q.strip()
    if not query:
        raise bad_request("搜索词不能为空", {"q": q})
    rows = ctx.store.db.query(
        """
        SELECT sentence_id, chapter_id, chapter_title, text
        FROM sentences
        WHERE book_id = ? AND instr(lower(text), lower(?)) > 0
        ORDER BY chapter_index, ord, sent_index
        LIMIT ?
        """,
        (book_id, query, limit),
    )
    results = [
        SearchResult(
            sentence_id=row["sentence_id"],
            chapter_id=row["chapter_id"],
            chapter_title=row["chapter_title"],
            snippet=_snippet(row["text"], query),
            before=_context(row["text"], query, before=True),
            after=_context(row["text"], query, before=False),
        )
        for row in rows
    ]
    total = ctx.store.db.query_one(
        "SELECT COUNT(*) AS n FROM sentences WHERE book_id = ? AND instr(lower(text), lower(?)) > 0",
        (book_id, query),
    )
    return SearchResponse(
        query=query, total=int(total["n"]) if total else 0, results=results
    )


def _snippet(text: str, query: str) -> str:
    """The hit with its query wrapped in ``<em>``."""
    position = text.lower().find(query.lower())
    if position < 0:
        return text[:SNIPPET_LENGTH]
    start = max(0, position - CONTEXT_LENGTH)
    end = min(len(text), position + len(query) + CONTEXT_LENGTH)
    before = text[start:position]
    hit = text[position : position + len(query)]
    after = text[position + len(query) : end]
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    return f"{prefix}{before}<em>{hit}</em>{after}{suffix}"


def _context(text: str, query: str, before: bool) -> str:
    """The plain text before or after the hit."""
    position = text.lower().find(query.lower())
    if position < 0:
        return ""
    if before:
        start = max(0, position - CONTEXT_LENGTH)
        return text[start:position]
    end = min(len(text), position + len(query) + CONTEXT_LENGTH)
    return text[position + len(query) : end]
