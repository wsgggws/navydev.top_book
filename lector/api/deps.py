"""Shared dependencies: context, authentication and rate limiting."""

from __future__ import annotations

import secrets
import time
from collections import defaultdict, deque
from dataclasses import dataclass

from fastapi import Request

from lector.api.errors import ApiError
from lector.audio import AudioService
from lector.config import Settings
from lector.db import Database
from lector.store import Store
from lector.tts.base import TTSEngine
from lector.tts.cache import AudioCache

#: Per-IP request budgets per minute.
UPLOAD_LIMIT = 10
READ_LIMIT = 600


@dataclass
class AppContext:
    """Everything the request handlers need."""

    settings: Settings
    db: Database
    store: Store
    cache: AudioCache
    engine: TTSEngine
    audio: AudioService
    limiter: RateLimiter


def get_context(request: Request) -> AppContext:
    """The application context of the running server."""
    return request.app.state.ctx


class RateLimiter:
    """A small in-memory per-IP rate limiter."""

    def __init__(self) -> None:
        self._hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)

    def check(self, bucket: str, client: str, limit: int, window: float = 60.0) -> None:
        """Raise a 429 when the client is over its budget."""
        now = time.monotonic()
        key = (bucket, client)
        hits = self._hits[key]
        while hits and now - hits[0] > window:
            hits.popleft()
        if len(hits) >= limit:
            retry_after = max(1, int(window - (now - hits[0])) + 1)
            raise ApiError(
                429,
                "RATE_LIMITED",
                "请求过于频繁，请稍后再试",
                {"retry_after": retry_after},
                headers={"Retry-After": str(retry_after)},
            )
        hits.append(now)


def client_address(request: Request) -> str:
    """The address the request came from."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _check_token(request: Request) -> None:
    """Enforce the bearer token when one is configured."""
    token = get_context(request).settings.token
    if not token:
        return
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise ApiError(401, "UNAUTHORIZED", "缺少访问令牌")
    provided = header[7:].strip()
    if not secrets.compare_digest(provided, token):
        raise ApiError(401, "UNAUTHORIZED", "访问令牌无效")


async def require_auth(request: Request) -> None:
    """Authenticate the request and charge it to the read budget."""
    _check_token(request)
    ctx = get_context(request)
    ctx.limiter.check("read", client_address(request), READ_LIMIT)


async def require_auth_upload(request: Request) -> None:
    """Authenticate an upload and charge it to the upload budget."""
    _check_token(request)
    ctx = get_context(request)
    ctx.limiter.check("upload", client_address(request), UPLOAD_LIMIT)
