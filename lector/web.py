"""The FastAPI application.

``uvicorn lector.web:app`` starts the server; the browser application in
``web/`` is mounted at the root and the API lives under ``/api/v1``.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from lector.api import ROUTERS
from lector.api.deps import AppContext, RateLimiter, require_auth
from lector.api.errors import ApiError
from lector.config import APP_VERSION, PARSER_VERSION, Settings, ensure_dirs, load_settings
from lector.db import Database
from lector.store import Store
from lector.tts.base import TTSEngine
from lector.tts.cache import AudioCache
from lector.tts.edge import EdgeTTSEngine
from lector.tts.espeak import EspeakEngine
from lector.audio import AudioService

logger = logging.getLogger("lector")

API_PREFIX = "/api/v1"


def build_engine(settings: Settings) -> TTSEngine:
    """Pick the synthesis engine the configuration asks for."""
    if settings.tts_engine == "espeak":
        return EspeakEngine()
    if settings.tts_engine == "auto":
        espeak = EspeakEngine()
        if espeak.available:
            return espeak
        return EdgeTTSEngine()
    return EdgeTTSEngine()


def create_app(settings: Settings | None = None) -> FastAPI:
    """Assemble the application."""
    settings = settings or load_settings()
    ensure_dirs(settings)

    db = Database(settings.db_path)
    db.init_schema()
    store = Store(settings, db)
    cache = AudioCache(settings.audio_dir)
    engine = build_engine(settings)
    audio = AudioService(settings, store, cache, engine)

    app = FastAPI(
        title="Lector",
        version=APP_VERSION,
        description="EPUB 阅读器 + 有声书播放器",
    )
    app.state.ctx = AppContext(
        settings=settings,
        db=db,
        store=store,
        cache=cache,
        engine=engine,
        audio=audio,
        limiter=RateLimiter(),
    )

    @app.exception_handler(ApiError)
    async def _handle_api_error(request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, ApiError)
        return exc.to_response()

    @app.exception_handler(RequestValidationError)
    async def _handle_validation(request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, RequestValidationError)
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "字段校验失败",
                    "detail": {"errors": _clean_errors(exc)},
                }
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http(request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, StarletteHTTPException)
        codes = {404: "NOT_FOUND", 401: "UNAUTHORIZED", 405: "BAD_REQUEST"}
        code = codes.get(exc.status_code, "INTERNAL_ERROR")
        messages = {
            404: "资源不存在",
            401: "缺少或错误的访问令牌",
            405: "请求方法不被支持",
        }
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": code,
                    "message": messages.get(exc.status_code, exc.detail),
                }
            },
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("未处理的异常", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "服务端异常",
                    "detail": {"request_id": _request_id(request)},
                }
            },
        )

    for router in ROUTERS:
        app.include_router(router, prefix=API_PREFIX)

    @app.get("/s/{code}", include_in_schema=False)
    async def share_link(code: str) -> RedirectResponse:
        """Open a shared position in the browser application."""
        return RedirectResponse(url=f"/?s={code}")

    @app.get("/api/v1/meta", include_in_schema=False)
    async def meta(request: Request) -> dict:
        """Build information for the browser application."""
        await require_auth(request)
        return {
            "version": APP_VERSION,
            "parser_version": PARSER_VERSION,
            "default_voice": settings.default_voice,
        }

    web_dir = Path(settings.web_dir)
    if web_dir.exists():
        app.mount("/", StaticFiles(directory=str(web_dir), html=True), name="web")
    return app


def _clean_errors(exc: RequestValidationError) -> list[dict]:
    """Make pydantic's error list JSON friendly."""
    cleaned = []
    for error in exc.errors():
        cleaned.append(
            {
                "loc": [str(part) for part in error.get("loc", [])],
                "msg": str(error.get("msg", "")),
                "type": str(error.get("type", "")),
            }
        )
    return cleaned


def _request_id(request: Request) -> str:
    """A cheap request id for error reports."""
    return request.headers.get("x-request-id", "") or f"req-{id(request):x}"


def main() -> None:
    """Entry point of the server (``uv run lector-server``)."""
    import uvicorn

    settings = load_settings()
    uvicorn.run(
        "lector.web:app",
        host=settings.host,
        port=settings.port,
        reload=bool(os.environ.get("LECTOR_RELOAD")),
    )


app = create_app()
