"""Lector — the terminal client.

It talks to the same content API as the browser, but keeps its reading position
in a local progress file so the two clients never overwrite each other.
"""

from lector_tui.app import LectorApp

__all__ = ["LectorApp"]
