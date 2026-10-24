"""The error envelope.

Every non-2xx response looks the same: ``{"error": {"code", "message", "detail"}}``.
Clients branch on ``code`` and never on ``message``.
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse


class ApiError(Exception):
    """An error that maps onto the contract's error table."""

    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        detail: dict | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.detail = detail
        self.headers = headers or {}

    def to_response(self) -> JSONResponse:
        payload: dict[str, object] = {"code": self.code, "message": self.message}
        if self.detail:
            payload["detail"] = self.detail
        return JSONResponse(
            status_code=self.status,
            content={"error": payload},
            headers=self.headers or None,
        )


def bad_request(message: str, detail: dict | None = None) -> ApiError:
    return ApiError(400, "BAD_REQUEST", message, detail)


def not_found(message: str = "资源不存在", detail: dict | None = None) -> ApiError:
    return ApiError(404, "NOT_FOUND", message, detail)


def validation_error(message: str, detail: dict | None = None) -> ApiError:
    return ApiError(422, "VALIDATION_ERROR", message, detail)


def epub_invalid(message: str, detail: dict | None = None) -> ApiError:
    return ApiError(422, "EPUB_INVALID", message, detail)


async def api_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Render an :class:`ApiError` as the standard envelope."""
    assert isinstance(exc, ApiError)
    return exc.to_response()
