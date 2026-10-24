"""The FastAPI application.

``uvicorn lector.web:app`` starts the server; the browser application in
``web/`` is mounted at the root and the API lives under ``/api/v1``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from lector.api import ROUTERS
from lector.api.deps import AppContext, RateLimiter, parse_token, public_read
from lector.api.errors import ApiError
from lector.config import (
    APP_VERSION,
    DEFAULT_RATE_BY_LOCALE,
    DEFAULT_VOICE_BY_LOCALE,
    FEATURED_VOICES,
    PARSER_VERSION,
    Settings,
    ensure_dirs,
    load_settings,
)
from lector.db import Database
from lector.epub.errors import EpubError
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
    base = settings.base_path

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
        app.include_router(router, prefix=f"{base}{API_PREFIX}")

    @app.get(f"{base}/s/{{code}}", include_in_schema=False)
    async def share_link(code: str) -> RedirectResponse:
        """Open a shared position in the browser application."""
        return RedirectResponse(url=f"{base}/?s={code}")

    @app.get(f"{base}/api/v1/meta", include_in_schema=False)
    async def meta(request: Request) -> dict:
        """Build information for the browser application."""
        await public_read(request)
        return {
            "version": APP_VERSION,
            "parser_version": PARSER_VERSION,
            "default_voice": settings.default_voice,
            "featured_voices": list(FEATURED_VOICES),
            "default_voices": dict(DEFAULT_VOICE_BY_LOCALE),
            "default_rates": dict(DEFAULT_RATE_BY_LOCALE),
            "scope": parse_token(settings.token).scope,
        }

    web_dir = Path(settings.web_dir)
    if web_dir.exists():
        asset_version = _web_asset_version(web_dir)

        async def index() -> HTMLResponse:
            """The application shell.

            The base path is injected here: the client needs to know it to
            build the API URLs when the app is served under a prefix
            (for example behind nginx at ``/book``).
            """
            markup = (web_dir / "index.html").read_text("utf-8")
            page_base = f"{base}/" if base else "/"
            import_map = _asset_import_map(web_dir, base, asset_version)
            head = (
                f'<base href="{page_base}">\n'
                f"<script>window.lectorBase={json.dumps(base)}</script>\n"
                f'<script type="importmap">{import_map}</script>'
            )
            markup = markup.replace("<head>", f"<head>\n{head}", 1)
            markup = _version_assets(markup, asset_version)
            return HTMLResponse(markup, headers={"Cache-Control": "no-cache"})

        app.add_api_route(f"{base}/", index, include_in_schema=False)
        # `/book` and `/book/` must both render the shell directly; a redirect
        # would make relative asset URLs resolve against `/` instead of `/book/`.
        if base:
            app.add_api_route(base, index, include_in_schema=False)

        app.mount(base or "/", StaticFiles(directory=str(web_dir), html=True), name="web")
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


def _web_asset_version(web_dir: Path) -> str:
    """Hash the browser assets so every deploy gets fresh URLs."""
    digest = hashlib.sha256()
    for path in sorted(web_dir.rglob("*")):
        if path.is_file() and path.suffix in {".css", ".js"}:
            digest.update(path.relative_to(web_dir).as_posix().encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


def _version_assets(markup: str, version: str) -> str:
    """Append the content version to local CSS and module script URLs."""
    pattern = r'((?:href|src)=")((?:styles|js)/[^"?]+)(?:\?[^"]*)?(")'
    return re.sub(pattern, rf"\1\2?v={version}\3", markup)


def _asset_import_map(web_dir: Path, base: str, version: str) -> str:
    """Map every ES module URL to its content-versioned form."""
    modules = {}
    for path in sorted(web_dir.rglob("*.js")):
        relative = path.relative_to(web_dir).as_posix()
        url = f"{base}/{relative}"
        modules[url] = f"{url}?v={version}"
    return json.dumps({"imports": modules}, separators=(",", ":"))


def sync_seed_books(store: Store, directory: Path | None) -> None:
    """Import EPUBs shipped in the repository into the writable library.

    Content hashes make this idempotent. A malformed file is reported and
    skipped so one bad addition cannot stop the server from starting.
    """
    if directory is None or not directory.is_dir():
        return
    for path in sorted(directory.glob("*.epub")):
        try:
            result = store.ingest(path.read_bytes())
        except (OSError, EpubError) as exc:
            logger.error("仓库书籍导入失败 %s: %s", path.name, exc)
            continue
        if not result.duplicate:
            logger.info("已导入仓库书籍《%s》", result.book.title)


def main() -> None:
    """Entry point of the server (``uv run lector-server``)."""
    import uvicorn

    settings = load_settings()
    sync_seed_books(app.state.ctx.store, settings.seed_books_dir)
    if not settings.token and settings.host not in ("127.0.0.1", "localhost", "::1"):
        logger.warning(
            "LECTOR_TOKEN 未设置，服务将向 %s 开放且任何人都能读写全部书籍。"
            "线上部署请务必设置令牌，或把 LECTOR_HOST 收回 127.0.0.1 并交给反向代理。",
            settings.host,
        )
    uvicorn.run(
        "lector.web:app",
        host=settings.host,
        port=settings.port,
        reload=bool(os.environ.get("LECTOR_RELOAD")),
    )


app = create_app()
