"""PNG detail and lifecycle at the Textual/tmux image boundary."""

import asyncio
import subprocess

import pytest
from textual.geometry import Region
from textual.screen import Screen
from textual.widgets import Static

from lector_tui.tmux_images import PaneGeometry, pane_geometry, passthrough


@pytest.mark.parametrize("status,lines,top", [("bottom", "on", 4), ("top", "on", 5), ("top", "2", 6)])
def test_pane_geometry_accounts_for_splits_and_top_status(monkeypatch, status, lines, top):
    monkeypatch.setenv("TMUX", "/tmp/isolated,1,0")
    monkeypatch.setenv("TMUX_PANE", "%3")
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, f"on\t1\t0\t1\t20\t4\t60\t18\t{status}\t{lines}\n")

    monkeypatch.setattr(subprocess, "run", run)
    assert pane_geometry() == PaneGeometry(20, top, 60, 18)
    assert len(commands) == 1 and commands[0][1] == "display-message"


@pytest.mark.parametrize("metadata", [
    "off\t1\t0\t1\t0\t0\t80\t24\tbottom\ton",
    "on\t0\t0\t1\t0\t0\t80\t24\tbottom\ton",
    "on\t1\t1\t0\t0\t0\t80\t24\tbottom\ton",
    "on\t1\t0\t1\t-1\t0\t80\t24\tbottom\ton",
    "on\t1\t0\t1\t0\t0\t0\t24\tbottom\ton",
    "unsupported tmux version",
])
def test_hidden_or_unavailable_pane_never_paints_over_another_window(monkeypatch, metadata):
    monkeypatch.setenv("TMUX", "/tmp/isolated,1,0")
    monkeypatch.setenv("TMUX_PANE", "%3")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, metadata))
    assert pane_geometry() is None


def test_passthrough_quotes_every_escape_and_restores_cursor():
    sequence = "\x1b_Ga=d,d=I,i=123,q=2\x1b\\"
    encoded = passthrough(sequence)
    assert encoded.startswith("\x1bPtmux;") and encoded.endswith("\x1b\\")
    assert encoded[7:-2].replace("\x1b\x1b", "\x1b") == "\x1b7\x1b[?2026h" + sequence + "\x1b[?2026l\x1b8"


def test_large_png_uses_small_envelopes_and_repeats_placement_coordinates():
    position = "\x1b[5;24H"
    packets = "".join("\x1b_Gq=2,m=1;" + "A" * 4096 + "\x1b\\" for _ in range(300))
    envelopes = passthrough(position + packets).split("\x1bPtmux;")[1:]
    assert len(envelopes) == 300
    assert all(len(envelope) < 8192 for envelope in envelopes)
    for envelope in envelopes:
        decoded = envelope[:-2].replace("\x1b\x1b", "\x1b")
        assert position in decoded
        assert decoded.startswith("\x1b7") and decoded.endswith("\x1b8")


def test_inline_images_coalesce_scrolls_and_release_old_screen(monkeypatch):
    from PIL import Image
    from lector_tui import image_widget, terminal_graphics
    from lector_tui.image_app import ImageApp
    from lector_tui.image_widget import WholeInlineImage, _WholeInlinePNG
    from lector_tui.widgets import ImageScroll
    from textual.app import App

    geometry = PaneGeometry(20, 2, 80, 30)
    monkeypatch.setattr(terminal_graphics, "inline_png", True)
    monkeypatch.setattr(image_widget, "pane_geometry", lambda: geometry)
    monkeypatch.setattr("lector_tui.tmux_images.pane_geometry", lambda: geometry)

    class Host(ImageApp):
        CSS = "ImageScroll {width:40;height:18;} WholeInlineImage {width:30;height:12;} Static {height:auto;}"

        def compose(self):
            yield ImageScroll(Static("before\n" * 3), WholeInlineImage(Image.new("RGB", (300, 240), "red")), Static("after\n" * 30))

    async def scenario():
        app = Host()
        writes = []
        def display(self, screen, update):
            if update is not None:
                writes.append(update.render_segments(self.console))

        monkeypatch.setattr(App, "_display", display)
        async with app.run_test(size=(100, 30)) as pilot:
            monkeypatch.setattr(app._driver, "write", writes.append)
            app.action_refresh_images()
            await pilot.pause(.12)
            image = app.query_one(_WholeInlinePNG)
            assert any("a=T,f=100" in value for value in writes)
            assert image in app._inline_drawn
            pane = app.query_one(ImageScroll)
            writes.clear()
            pane.scroll_to(y=4, animate=False)
            await pilot.pause(.01)
            pane.scroll_to(y=6, animate=False)
            await pilot.pause(.12)
            assert sum(value.count("a=T,f=100") for value in writes) <= 2
            assert image._placement[0] == app.screen.find_widget(image).visible_region
            writes.clear()
            # A queued old-screen image must not be painted after a screen swap.
            image.refresh(Region(0, 0, 30, 1))
            app.push_screen(Screen(Static("another page")))
            await pilot.pause(.12)
            assert any(f"a=d,d=I,i={image.image_id},q=2" in value for value in writes)
            assert not any("a=T,f=100" in value for value in writes)
            assert not app._inline_drawn
            app.pop_screen()
            await pilot.pause(.12)
            assert image in app._inline_drawn
            writes.clear()
            geometry_backup = geometry
            # Simulate a tmux window switch between layout and deferred output.
            monkeypatch.setattr("lector_tui.tmux_images.pane_geometry", lambda: None)
            app.queue_inline_image(image, image._placement, geometry_backup, "STALE_IMAGE")
            await pilot.pause(.12)
            assert "STALE_IMAGE" not in "".join(writes)

    asyncio.run(scenario())
