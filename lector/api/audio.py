"""Sentence audio: the tiles the player streams."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, Response

from lector.api.deps import AppContext, get_context, public_read, require_admin
from lector.api.errors import ApiError
from lector.config import DEFAULT_RATE_BY_LOCALE
from lector.models import WarmRequest, WarmResponse, WordsResponse
from lector.tts.base import TTSError, TTSTimeout, TTSUnavailable

router = APIRouter(tags=["audio"])


async def _voice_for(ctx: AppContext, book_id: str, voice_id: str | None) -> str:
    """Which voice to synthesise with.

    The client may name one (``?voice_id=``); otherwise the book's own choice
    is used, and failing that the language decides.
    """
    if voice_id:
        return voice_id
    row = ctx.store.db.query_one(
        "SELECT voice_id FROM books WHERE book_id = ?", (book_id,)
    )
    preferred = row["voice_id"] if row else None
    book = ctx.store.get_book(book_id)
    return await ctx.audio.choose_voice(book.language if book else None, preferred)


def _default_rate(language: str | None) -> str:
    """The baseline TTS rate for a book language."""
    if not language:
        return "+0%"
    return DEFAULT_RATE_BY_LOCALE.get(language.split("-")[0].lower(), "+0%")


def require_book(ctx: AppContext, book_id: str):
    book = ctx.store.get_book(book_id)
    if book is None:
        raise ApiError(404, "NOT_FOUND", "书籍不存在", {"book_id": book_id})
    return book


@router.get("/books/{book_id}/audio/{sentence_id}.mp3")
async def get_audio(
    book_id: str,
    sentence_id: str,
    request: Request,
    voice_id: str | None = Query(None, description="用哪个音色合成；缺省按书的语言定"),
    rate: str | None = Query(None, description="合成语速，如 +10%"),
    _: None = Depends(public_read),
) -> Response:
    """The MP3 of one sentence.  The first request synthesises it."""
    ctx = get_context(request)
    book = require_book(ctx, book_id)
    voice = await _voice_for(ctx, book_id, voice_id)
    rate = rate or _default_rate(book.language)
    try:
        tile = await ctx.audio.tile(book_id, sentence_id, voice, rate)
    except TTSTimeout as exc:
        raise ApiError(504, "TTS_TIMEOUT", str(exc)) from exc
    except TTSUnavailable as exc:
        raise ApiError(503, "TTS_UNAVAILABLE", str(exc)) from exc
    except TTSError as exc:
        raise ApiError(503, "TTS_UNAVAILABLE", str(exc)) from exc
    if tile is None:
        raise ApiError(
            404, "NOT_FOUND", "句子不存在", {"book_id": book_id, "sentence_id": sentence_id}
        )
    return Response(
        content=tile.audio,
        media_type="audio/mpeg",
        headers={
            "Content-Length": str(len(tile.audio)),
            "Cache-Control": "public, max-age=31536000, immutable",
        },
    )


@router.get("/books/{book_id}/audio/{sentence_id}.words", response_model=WordsResponse)
async def get_words(
    book_id: str,
    sentence_id: str,
    request: Request,
    voice_id: str | None = Query(None, description="用哪个音色合成；缺省按书的语言定"),
    rate: str | None = Query(None, description="合成语速，如 +10%"),
    _: None = Depends(public_read),
) -> WordsResponse:
    """The word boundaries of one sentence — the data behind the highlight."""
    ctx = get_context(request)
    book = require_book(ctx, book_id)
    voice = await _voice_for(ctx, book_id, voice_id)
    rate = rate or _default_rate(book.language)
    try:
        tile = await ctx.audio.tile(book_id, sentence_id, voice, rate)
    except TTSTimeout as exc:
        raise ApiError(504, "TTS_TIMEOUT", str(exc)) from exc
    except TTSError as exc:
        raise ApiError(503, "TTS_UNAVAILABLE", str(exc)) from exc
    if tile is None:
        raise ApiError(
            404, "NOT_FOUND", "句子不存在", {"book_id": book_id, "sentence_id": sentence_id}
        )
    return WordsResponse(
        sentence_id=sentence_id,
        duration=tile.duration,
        words=[
            {"text": word.text, "start": word.start, "end": word.end} for word in tile.words
        ],
        granularity=tile.granularity,
    )


@router.post("/books/{book_id}/audio/warm", response_model=WarmResponse)
async def warm_audio(
    book_id: str,
    payload: WarmRequest,
    request: Request,
    _: None = Depends(require_admin),
) -> WarmResponse:
    """Pre-synthesise a chapter or the whole book."""
    ctx = get_context(request)
    require_book(ctx, book_id)
    row = ctx.store.db.query_one(
        "SELECT voice_id, language FROM books WHERE book_id = ?", (book_id,)
    )
    voice = await ctx.audio.choose_voice(row["language"], payload.voice_id or row["voice_id"])
    rate = payload.rate or _default_rate(row["language"])
    with ctx.store.db.write() as conn:
        conn.execute(
            "UPDATE books SET voice_id = ?, updated_at = updated_at WHERE book_id = ?",
            (voice, book_id),
        )
    if payload.chapter_id:
        sentence_ids = ctx.store.chapter_sentences(book_id, payload.chapter_id)
    else:
        sentence_ids = [
            row["sentence_id"]
            for row in ctx.store.db.query(
                "SELECT sentence_id FROM sentences WHERE book_id = ? ORDER BY chapter_index, ord",
                (book_id,),
            )
        ]
    if payload.limit:
        # 一次只预热一小段，客户端可以在后台接着叫下一段。
        sentence_ids = sentence_ids[: payload.limit]
    ready = 0
    failed = 0
    for sentence_id in sentence_ids:
        tile = None
        # The engine occasionally stalls on a short sentence; one retry is
        # cheap here because this call is a background job.
        for _attempt in range(2):
            try:
                tile = await ctx.audio.tile(book_id, sentence_id, voice, rate)
                break
            except TTSError:
                continue
        if tile is None:
            failed += 1
            continue
        ready += 1
    state = ctx.audio.book_state(book_id)
    return WarmResponse(queued=len(sentence_ids), ready=ready, failed=failed, state=state)


@router.delete("/books/{book_id}/audio", status_code=204)
async def clear_audio(
    book_id: str,
    request: Request,
    _: None = Depends(require_admin),
) -> Response:
    """Drop every synthesised tile of a book — used after changing the voice."""
    ctx = get_context(request)
    require_book(ctx, book_id)
    ctx.audio.clear_book(book_id)
    return Response(status_code=204)
