"""The HTTP layer."""

from lector.api import audio, books, chapters, progress, search, shortcodes, system

ROUTERS = (
    books.router,
    chapters.router,
    audio.router,
    progress.router,
    search.router,
    shortcodes.router,
    system.router,
)

__all__ = ["ROUTERS"]
