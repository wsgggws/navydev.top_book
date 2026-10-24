"""Health and voice listing."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from lector.api.deps import get_context, public_read
from lector.api.errors import ApiError
from lector.models import HealthResponse, TtsHealth, VoicesResponse
from lector.tts.base import TTSError

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    """Is the server alive, and can it speak?"""
    ctx = get_context(request)
    available = True
    voice_count = 0
    try:
        voices = await ctx.audio.voices()
        voice_count = len(voices)
    except TTSError:
        available = False
    status = "ok" if available else "degraded"
    return HealthResponse(
        status=status,
        version=_version(),
        parser_version=_parser_version(),
        tts=TtsHealth(engine=ctx.engine.name, available=available, voice_count=voice_count),
        books=ctx.store.count_books(),
    )


@router.get("/tts/voices", response_model=VoicesResponse)
async def voices(request: Request, _: None = Depends(public_read)) -> VoicesResponse:
    """The voices the engine offers."""
    ctx = get_context(request)
    try:
        voice_list = await ctx.audio.voices()
    except TTSError as exc:
        raise ApiError(503, "TTS_UNAVAILABLE", str(exc)) from exc
    return VoicesResponse(engine=ctx.engine.name, voices=voice_list)


def _version() -> str:
    from lector.config import APP_VERSION

    return APP_VERSION


def _parser_version() -> int:
    from lector.config import PARSER_VERSION

    return PARSER_VERSION
