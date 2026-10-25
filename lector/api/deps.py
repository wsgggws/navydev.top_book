"""Shared dependencies: context, authentication and rate limiting."""

from __future__ import annotations

import secrets
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from ipaddress import ip_address

from fastapi import Request

from lector.api.errors import ApiError
from lector.audio import AudioService
from lector.config import SCOPE_ADMIN, SCOPE_READER, SCOPES, Settings, is_local_host
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
    # Uvicorn resolves forwarding headers only for configured trusted peers.
    return request.client.host if request.client else "unknown"


def is_local_development(request: Request) -> bool:
    """The no-token exception is limited to direct loopback development."""
    settings = get_context(request).settings
    if settings.host not in ("127.0.0.1", "localhost", "::1"):
        return False
    if not is_local_host(request.headers.get("host")):
        return False
    if any(name == "forwarded" or name.startswith("x-forwarded-") for name in request.headers):
        return False
    try:
        return request.client is not None and ip_address(request.client.host).is_loopback
    except ValueError:
        return False


@dataclass(frozen=True)
class Credentials:
    """The caller's token and what it is allowed to do."""

    token: str
    scope: str = SCOPE_ADMIN


def parse_token(raw: str) -> Credentials:
    """Split ``<token>:reader`` into its parts.

    A token without a known scope suffix is an admin token, which keeps the
    old single-token setups working unchanged.
    """
    if not raw:
        return Credentials(token="", scope=SCOPE_ADMIN)
    token, sep, suffix = raw.rpartition(":")
    if sep and suffix in SCOPES:
        return Credentials(token=token, scope=suffix)
    return Credentials(token=raw, scope=SCOPE_ADMIN)


def _credentials(request: Request) -> Credentials:
    """Authenticate the request and return the caller's permissions."""
    ctx = get_context(request)
    configured = parse_token(ctx.settings.token)
    if not configured.token:
        if not is_local_development(request):
            raise ApiError(
                403,
                "ADMIN_DISABLED",
                "服务端未配置 LECTOR_TOKEN，管理写接口已禁用",
            )
        return Credentials(token="", scope=SCOPE_ADMIN)
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise ApiError(401, "UNAUTHORIZED", "缺少访问令牌")
    provided = header[7:].strip()
    # 权限后缀是服务端自己的配置，客户端只送密钥本身。
    if not secrets.compare_digest(
        provided.encode("utf-8"), configured.token.encode("utf-8")
    ):
        raise ApiError(401, "UNAUTHORIZED", "访问令牌无效")
    return configured


async def require_auth(request: Request) -> None:
    """Authenticate the request and charge it to the read budget."""
    _credentials(request)
    ctx = get_context(request)
    ctx.limiter.check("read", client_address(request), READ_LIMIT)


async def public_read(request: Request) -> None:
    """Rate-limit a public read without requiring an access token."""
    ctx = get_context(request)
    ctx.limiter.check("read", client_address(request), READ_LIMIT)


async def require_reader(request: Request) -> None:
    """A reader may read and record its own position, but not change the library."""
    credentials = _credentials(request)
    if credentials.scope not in (SCOPE_READER, SCOPE_ADMIN):
        raise ApiError(403, "FORBIDDEN", "该令牌没有写权限")
    ctx = get_context(request)
    ctx.limiter.check("read", client_address(request), READ_LIMIT)


async def require_admin(request: Request) -> None:
    """Only an admin token may change the library."""
    credentials = _credentials(request)
    if credentials.scope != SCOPE_ADMIN:
        raise ApiError(403, "FORBIDDEN", "该令牌没有管理权限")
    ctx = get_context(request)
    ctx.limiter.check("read", client_address(request), READ_LIMIT)


async def require_auth_upload(request: Request) -> None:
    """Authenticate an upload and charge it to the upload budget."""
    credentials = _credentials(request)
    if credentials.scope != SCOPE_ADMIN:
        raise ApiError(403, "FORBIDDEN", "该令牌没有管理权限")
    ctx = get_context(request)
    ctx.limiter.check("upload", client_address(request), UPLOAD_LIMIT)
