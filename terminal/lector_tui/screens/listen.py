"""Screen three — listening.

It lives in its own module because the interface specification names it as a
screen of its own; the implementation shares the reading screen.
"""

from lector_tui.screens.reader import ListenScreen

__all__ = ["ListenScreen"]
