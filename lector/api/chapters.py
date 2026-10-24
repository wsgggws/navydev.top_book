"""Chapters, table of contents and the audio timeline."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from lector.api.deps import AppContext, get_context, public_read
from lector.api.errors import ApiError
from lector.audio import INTER_SENTENCE_GAP
from lector.models import ChapterResponse, TimelineEntry, TimelineResponse, TocResponse

router = APIRouter(tags=["chapters"])


def require_book(ctx: AppContext, book_id: str):
    """Return the book or raise a 404."""
    book = ctx.store.get_book(book_id)
    if book is None:
        raise ApiError(404, "NOT_FOUND", "书籍不存在", {"book_id": book_id})
    return book


@router.get("/books/{book_id}/toc", response_model=TocResponse)
async def get_toc(
    book_id: str,
    request: Request,
    _: None = Depends(public_read),
) -> TocResponse:
    """The navigation tree.

    A node's ``id`` is not a chapter id: clients resolve a node by taking its
    ``chapter_id`` and then, if it has one, the ``anchor`` inside it.
    """
    ctx = get_context(request)
    require_book(ctx, book_id)
    return TocResponse(toc=ctx.store.load_toc(book_id))


@router.get("/books/{book_id}/chapters/{chapter_id}", response_model=ChapterResponse)
async def get_chapter(
    book_id: str,
    chapter_id: str,
    request: Request,
    _: None = Depends(public_read),
) -> ChapterResponse:
    """One chapter with its blocks and sentences."""
    ctx = get_context(request)
    require_book(ctx, book_id)
    chapter = ctx.store.load_chapter(book_id, chapter_id)
    if chapter is None:
        raise ApiError(
            404, "NOT_FOUND", "章节不存在", {"book_id": book_id, "chapter_id": chapter_id}
        )
    ids = ctx.store.chapter_ids(book_id)
    index = ids.index(chapter_id) if chapter_id in ids else -1
    prev_id = ids[index - 1] if 0 < index < len(ids) else None
    next_id = ids[index + 1] if 0 <= index < len(ids) - 1 else None
    chapter.audio_duration = _chapter_duration(ctx, book_id, chapter_id)
    chapter.tts_state = ctx.audio.book_state(book_id)
    return ChapterResponse(chapter=chapter, prev_chapter_id=prev_id, next_chapter_id=next_id)


@router.get(
    "/books/{book_id}/chapters/{chapter_id}/timeline", response_model=TimelineResponse
)
async def get_timeline(
    book_id: str,
    chapter_id: str,
    request: Request,
    _: None = Depends(public_read),
) -> TimelineResponse:
    """The audio timeline of a chapter.

    Only sentences that have been synthesised appear; the array can therefore
    be played straight through.
    """
    ctx = get_context(request)
    require_book(ctx, book_id)
    if ctx.store.load_chapter(book_id, chapter_id) is None:
        raise ApiError(
            404, "NOT_FOUND", "章节不存在", {"book_id": book_id, "chapter_id": chapter_id}
        )
    entries: list[TimelineEntry] = []
    cursor = 0.0
    for sentence_id in ctx.store.chapter_sentences(book_id, chapter_id):
        duration = ctx.audio.tile_duration(book_id, sentence_id)
        if duration is None:
            continue
        entries.append(
            TimelineEntry(
                sentence_id=sentence_id,
                start=round(cursor, 3),
                end=round(cursor + duration, 3),
                audio_url=(
                    f"{ctx.settings.base_path}/api/v1/books/{book_id}/audio/{sentence_id}.mp3"
                ),
                word_count=_word_count(ctx, book_id, sentence_id),
            )
        )
        cursor += duration + INTER_SENTENCE_GAP
    return TimelineResponse(
        chapter_id=chapter_id,
        duration=round(cursor, 3),
        sentences=entries,
        tts_state=ctx.audio.book_state(book_id),
    )


def _chapter_duration(ctx: AppContext, book_id: str, chapter_id: str) -> float:
    """Total duration of the synthesised sentences of a chapter."""
    total = 0.0
    for sentence_id in ctx.store.chapter_sentences(book_id, chapter_id):
        duration = ctx.audio.tile_duration(book_id, sentence_id)
        if duration is not None:
            total += duration
    return round(total, 3)


def _word_count(ctx: AppContext, book_id: str, sentence_id: str) -> int:
    """Number of words in a sentence, counted the same way the parser does."""
    from lector.epub.sentences import split_words

    text = ctx.store.sentence_text(book_id, sentence_id)
    if not text:
        return 0
    return len(split_words(text))
