"""Errors raised while reading an EPUB.

``code`` values map onto the API error table in ``docs/API.md``.
"""

from __future__ import annotations


class EpubError(Exception):
    """Base class for every recoverable EPUB problem."""

    code = "EPUB_INVALID"
    status = 422

    def __init__(self, message: str, detail: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail or {}


class EpubStructureError(EpubError):
    """The container, OPF or spine is missing or malformed."""


class EpubSecurityError(EpubError):
    """The archive tried to escape the extraction root or explode in size."""


class EpubNotAZipError(EpubError):
    """The uploaded file is not a ZIP container at all."""

    code = "UNSUPPORTED_MEDIA_TYPE"
    status = 415
