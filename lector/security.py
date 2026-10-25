"""Browser-only guards and response hardening for the web application."""

from __future__ import annotations

import re
import secrets
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from lector.api.deps import parse_token
from lector.config import is_local_host

_CLI_USER_AGENT = re.compile(
    r"(?:curl|wget|python-requests|httpx|httpie|postmanruntime|"
    r"go-http-client|libwww-perl|java/|okhttp)",
    re.IGNORECASE,
)
_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

_CSP = (
    "default-src 'self'; "
    "base-uri 'self'; "
    "object-src 'none'; "
    "frame-ancestors 'self'; "
    "form-action 'self'; "
    "img-src 'self' data: blob:; "
    "media-src 'self' blob:; "
    "font-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "script-src 'self' 'unsafe-inline'; "
    "connect-src 'self'"
)


def install_security(app: FastAPI) -> None:
    """Reject obvious command-line browsing and enforce same-origin writes."""

    @app.middleware("http")
    async def security_middleware(request: Request, call_next):
        settings = request.app.state.ctx.settings
        path = request.url.path

        guard_enabled = bool(settings.token) or not is_local_host(
            request.headers.get("host")
        )
        if guard_enabled:
            user_agent = request.headers.get("user-agent", "")
            cli_client = not user_agent or _CLI_USER_AGENT.search(user_agent)
            relative = _relative_path(path, settings.base_path)
            is_health = relative == "/api/v1/health"
            is_terminal = request.headers.get("x-lector-client") == "terminal"
            if (
                cli_client
                and not is_health
                and not is_terminal
                and not _has_valid_token(request)
            ):
                return _secure_response(
                    _blocked("该入口只允许浏览器或官方客户端访问", "BROWSER_ONLY"),
                    request,
                )

        if (
            guard_enabled
            and request.method in _UNSAFE_METHODS
            and _is_api_path(path, settings.base_path)
            and not _has_valid_token(request)
            and not _is_same_origin(request)
        ):
            return _secure_response(
                _blocked("写请求必须来自同源浏览器", "SAME_ORIGIN_REQUIRED"),
                request,
            )

        response = await call_next(request)
        return _secure_response(response, request)

    return None


def _blocked(message: str, code: str) -> JSONResponse:
    return JSONResponse(
        status_code=403,
        content={"error": {"code": code, "message": message}},
    )


def _secure_response(response: Response, request: Request) -> Response:
    response.headers.setdefault("Content-Security-Policy", _CSP)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault(
        "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
    )
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
    response.headers.setdefault("X-Permitted-Cross-Domain-Policies", "none")
    forwarded_proto = request.headers.get("x-forwarded-proto", "").split(",", 1)[0]
    if request.url.scheme == "https" or forwarded_proto == "https":
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=15768000; includeSubDomains"
        )
    return response


def _is_api_path(path: str, base_path: str) -> bool:
    relative = _relative_path(path, base_path)
    return relative is not None and relative.startswith("/api/")


def _relative_path(path: str, base_path: str) -> str | None:
    if not base_path:
        return path
    if path == base_path:
        return "/"
    if path.startswith(f"{base_path}/"):
        return path[len(base_path):]
    return None


def _has_valid_token(request: Request) -> bool:
    configured = parse_token(request.app.state.ctx.settings.token).token
    header = request.headers.get("authorization", "")
    if not configured or not header.lower().startswith("bearer "):
        return False
    return secrets.compare_digest(header[7:].strip(), configured)


def _is_same_origin(request: Request) -> bool:
    fetch_site = request.headers.get("sec-fetch-site")
    if fetch_site and fetch_site != "same-origin":
        return False
    source = request.headers.get("origin") or request.headers.get("referer")
    if not source:
        return False
    parsed = urlsplit(source)
    return (
        parsed.scheme in ("http", "https")
        and parsed.netloc == request.url.netloc
    )
