"""Shared widgets."""

from __future__ import annotations

from textual.binding import Binding
from textual.widgets import ListView


class VimListView(ListView):
    """A list that also answers to vim's keys.

    Textual's list only knows the arrow keys, so without this the shelf and
    the directory cannot be moved around with ``j``/``k``.
    """

    BINDINGS = [
        Binding("j", "cursor_down", "下移"),
        Binding("k", "cursor_up", "上移"),
        Binding("l", "select_cursor", "进入"),
    ]
