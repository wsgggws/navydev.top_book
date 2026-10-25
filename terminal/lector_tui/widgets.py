"""Shared widgets."""

from __future__ import annotations

from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.widgets import ListView
from lector_tui.image_widget import TerminalImage


def refresh_visible_images(container: ListView | VerticalScroll) -> None:
    """Re-emit terminal graphics after the cells around them have moved."""
    try:
        images = container.query(TerminalImage)
    except Exception:  # noqa: BLE001 - the container may be closing
        return
    for image in images:
        try:
            if image.is_on_screen:
                image.refresh()
        except Exception:  # noqa: BLE001 - one failed repaint must not break scrolling
            continue


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

    def watch_scroll_y(self, old_value: float, new_value: float) -> None:
        super().watch_scroll_y(old_value, new_value)
        if round(old_value) != round(new_value):
            self.call_after_refresh(refresh_visible_images, self)


class ImageScroll(VerticalScroll):
    """A scroll container that repaints native images after scrolling."""

    def watch_scroll_y(self, old_value: float, new_value: float) -> None:
        super().watch_scroll_y(old_value, new_value)
        if round(old_value) != round(new_value):
            self.call_after_refresh(refresh_visible_images, self)
