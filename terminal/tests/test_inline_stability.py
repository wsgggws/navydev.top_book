"""Visible PNGs must survive the text frame while a scroll update is queued."""

import asyncio
import re
from types import SimpleNamespace

from PIL import Image
import pytest
from rich.segment import Segment
from textual._compositor import ChopsUpdate, LayoutUpdate
from rich.cells import get_character_cell_size
from textual.app import App
from textual.geometry import Region
from textual.strip import Strip
from textual.widgets import Static


def written_cells(sequence):
    """Track text writes in the compositor's output, excluding graphic packets."""
    x = y = 0
    cells = set()
    tokens = re.findall(r"\x1bP.*?\x1b\\|\x1b\[[0-?]*[ -/]*[@-~]|\x1b.|.", sequence, re.S)
    for token in tokens:
        if token.startswith("\x1b["):
            if token[-1] in {"H", "f"}:
                row, col = (token[2:-1] or "1;1").split(";")
                x, y = int(col) - 1, int(row) - 1
        elif token.startswith("\x1b"):
            continue
        elif token == "\n":
            y += 1
        elif token == "\r":
            x = 0
        else:
            width = get_character_cell_size(token)
            cells.update((x + offset, y) for offset in range(width))
            x += width
    return cells


@pytest.mark.parametrize("inline", [True, False])
def test_inline_png_avoids_tmux_synchronized_full_line_erases(monkeypatch, inline):
    from lector_tui import terminal_graphics
    from lector_tui.image_app import ImageApp

    monkeypatch.setattr(terminal_graphics, "inline_png", inline)
    app = ImageApp()
    writes = []
    app._driver = SimpleNamespace(write=writes.append)
    app._sync_available = True
    app._begin_update()
    app._end_update()
    assert writes == ([] if inline else ["\x1b[?2026h", "\x1b[?2026l"])


@pytest.mark.parametrize("kind", ["layout", "chops"])
def test_png_protection_preserves_unicode_text_and_foreground_overlay(kind):
    from rich.console import Console
    from lector_tui.image_widget import _text_around_images

    strip = Strip([Segment("左ABCDEFGHIJ右")])
    width = strip.cell_length
    if kind == "layout":
        update = LayoutUpdate([[strip]], Region(0, 2, width, 1))
    else:
        update = ChopsUpdate([{}, {}, {0: strip}], [(2, 0, width)], [[], [], [width]])
    visible = Region(2, 2, 10, 1)
    menu = Region(5, 2, 3, 1)
    output = _text_around_images(update, [(visible, (menu,))], Console())
    assert written_cells(output) == {(x, 2) for x in [0, 1, 5, 6, 7, 12, 13]}
    assert "左" in output and "右" in output and "DEF" in output


def test_scroll_keeps_png_visible_and_unrelated_refresh_does_not_retransmit(monkeypatch):
    from lector_tui import image_widget, terminal_graphics
    from lector_tui.image_app import ImageApp
    from lector_tui.image_widget import WholeInlineImage, _WholeInlinePNG
    from lector_tui.tmux_images import PaneGeometry
    from lector_tui.widgets import ImageScroll

    geometry = PaneGeometry(0, 0, 60, 24)
    monkeypatch.setattr(terminal_graphics, "inline_png", True)
    monkeypatch.setattr(image_widget, "pane_geometry", lambda: geometry)
    monkeypatch.setattr("lector_tui.tmux_images.pane_geometry", lambda: geometry)

    class Host(ImageApp):
        CSS = "ImageScroll {width:40;height:18;} WholeInlineImage {width:30;height:12;} Static {height:auto;}"

        def compose(self):
            yield ImageScroll(Static("before\n" * 3), WholeInlineImage(Image.new("RGB", (300, 240), "red")), Static("after\n" * 30))

    async def scenario():
        writes = []

        def display(self, screen, update):
            if update is not None:
                writes.append(update.render_segments(self.console))

        monkeypatch.setattr(App, "_display", display)
        app = Host()
        async with app.run_test(size=(60, 24)) as pilot:
            monkeypatch.setattr(app._driver, "write", writes.append)
            app.action_refresh_images()
            await pilot.pause(.12)
            image = app.query_one(_WholeInlinePNG)
            before = app.screen.find_widget(image).visible_region
            writes.clear()
            app.query_one(ImageScroll).scroll_to(y=1, animate=False)
            await pilot.pause(.12)
            after = app.screen.find_widget(image).visible_region
            assert before != after
            overlap = before.intersection(after)
            repainted = set().union(*(written_cells(frame) for frame in writes))
            erased = {(x, y) for x, y in repainted if overlap.contains(x, y)}
            assert not erased, f"scroll blanks {len(erased)} image cells before the deferred PNG replacement"
            assert any("a=T,f=100" in frame for frame in writes)

            writes.clear()
            app.screen.refresh()
            await pilot.pause(.12)
            assert not any("a=T,f=100" in frame for frame in writes), "unchanged PNG must survive text/selection refresh without re-upload"

    asyncio.run(scenario())
