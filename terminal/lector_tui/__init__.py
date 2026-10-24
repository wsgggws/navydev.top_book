"""Lector — the terminal client.

It talks to the same API as the browser and writes to the same progress, so
a reader can move between the two without losing their place.
"""

from lector_tui.app import LectorApp

__all__ = ["LectorApp"]
