"""Exercise native graphics at the actual Textual display boundary."""

import asyncio

from PIL import Image
import pytest
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.geometry import Region
from textual.widgets import Static

from lector_tui.image_app import ImageApp
from lector_tui.image_widget import WholeSixelImage, _WholeSixels
from lector_tui.widgets import ImageScroll


@pytest.fixture
def frames(monkeypatch):
    result = []

    def display(self, screen, update):
        if update is not None:
            result.append(update.render_segments(self.console))

    monkeypatch.setattr(App, "_display", display)
    return result


class ImageHost(ImageApp):
    CSS = """
    ImageScroll { width: 40; height: 18; }
    WholeSixelImage { width: 30; height: 12; }
    Static { height: auto; }
    #overlay { layer: overlay; position: absolute; offset: 5 7; width: 8; height: 3; display: none; }
    """
    BINDINGS = [Binding("j", "down"), Binding("k", "up")]

    def compose(self) -> ComposeResult:
        yield ImageScroll(
            Static("before\n" * 3),
            WholeSixelImage(Image.new("RGB", (300, 240), "red")),
            Static("after\n" * 30, id="after"),
        )
        yield Static("MENU", id="overlay")

    def action_down(self):
        self.query_one(ImageScroll).scroll_down(animate=False)

    def action_up(self):
        self.query_one(ImageScroll).scroll_up(animate=False)


def graphic_frames(frames):
    return [frame for frame in frames if "\x1bP" in frame]


def test_initial_load_and_each_scroll_draw_one_complete_image(frames):
    async def scenario():
        app = ImageHost()
        async with app.run_test(size=(80, 30)) as pilot:
            await pilot.pause()
            assert graphic_frames(frames)
            assert all(frame.count("\x1bP") == 1 for frame in graphic_frames(frames))
            impl = app.query_one(_WholeSixels)
            for key in ["j"] * 10 + ["k"] * 10:
                frames.clear()
                await pilot.press(key)
                await pilot.pause()
                painted = graphic_frames(frames)
                assert len(painted) == 1, "one scroll must not schedule another image refresh"
                frame = painted[0]
                assert frame.count("\x1bP") == 1
                assert frame.startswith("\x1b[?2026h") and frame.endswith("\x1b[?2026l")
                assert frame.rfind("\x1bP") > frame.rfind("after"), "graphics follow text clearing"
                visible = app.screen.find_widget(impl).visible_region
                from textual_image._terminal import get_cell_size

                cells = get_cell_size()
                assert f'"1;1;{visible.width * cells.width};{visible.height * cells.height}' in frame

    asyncio.run(scenario())


def test_one_dirty_image_row_repaints_the_whole_visible_bitmap(frames):
    async def scenario():
        app = ImageHost()
        async with app.run_test(size=(80, 30)) as pilot:
            await pilot.pause()
            impl = app.query_one(_WholeSixels)
            frames.clear()
            impl.refresh(Region(3, 4, 7, 1))
            await pilot.pause()
            painted = graphic_frames(frames)
            assert len(painted) == 1 and painted[0].count("\x1bP") == 1
            assert '"1;1;300;240' in painted[0]

    asyncio.run(scenario())


def test_unrelated_text_updates_do_not_retransmit_images(frames):
    async def scenario():
        app = ImageHost()
        async with app.run_test(size=(80, 30)) as pilot:
            await pilot.pause()
            frames.clear()
            app.query_one("#after", Static).update("AFTER\n" * 30)
            await pilot.pause()
            assert frames
            assert graphic_frames(frames) == []

    asyncio.run(scenario())


def test_image_replacement_preserves_the_native_widget(frames):
    async def scenario():
        app = ImageHost()
        async with app.run_test(size=(80, 30)) as pilot:
            await pilot.pause()
            image = app.query_one(WholeSixelImage)
            impl = image.query_one(_WholeSixels)
            frames.clear()
            image.image = Image.new("RGB", (300, 240), "blue")
            await pilot.pause()
            assert image.query_one(_WholeSixels) is impl
            assert graphic_frames(frames)
            assert all(frame.count("\x1bP") == 1 for frame in graphic_frames(frames))

    asyncio.run(scenario())


def test_overlay_masks_one_bitmap_without_painting_over_its_text(frames, monkeypatch):
    encoded = []
    original = _WholeSixels._image_to_sixels

    def encode(self, image, *args):
        encoded.append(image.copy())
        return original(self, image, *args)

    monkeypatch.setattr(_WholeSixels, "_image_to_sixels", encode)

    async def scenario():
        app = ImageHost()
        async with app.run_test(size=(80, 30)) as pilot:
            await pilot.pause()
            encoded.clear()
            frames.clear()
            overlay = app.query_one("#overlay")
            overlay.display = True
            await pilot.pause()
            assert encoded and encoded[-1].mode == "RGBA"
            alpha = encoded[-1].getchannel("A")
            assert alpha.getextrema() == (0, 255)
            assert any("MENU" in frame for frame in frames)
            assert all(frame.count("\x1bP") == 1 for frame in graphic_frames(frames))
            frames.clear()
            overlay.display = False
            await pilot.pause()
            assert graphic_frames(frames)

    asyncio.run(scenario())


def test_sixel_crop_cache_is_bounded_and_reuses_scroll_back(frames, monkeypatch):
    calls = []
    original = _WholeSixels._image_to_sixels

    def encode(self, image, *args):
        calls.append(image.size)
        return original(self, image, *args)

    monkeypatch.setattr(_WholeSixels, "_image_to_sixels", encode)

    async def scenario():
        app = ImageHost()
        async with app.run_test(size=(80, 30)) as pilot:
            await pilot.pause()
            calls.clear()
            await pilot.press("j", "k")
            await pilot.pause()
            assert calls == [], "moving a fully visible image reuses its encoded bitmap"
            for _ in range(20):
                await pilot.press("j")
            impl = app.query_one(_WholeSixels)
            assert len(impl._bitmaps) <= 8
            assert impl._bitmap_bytes <= 8 * 1024 * 1024

    asyncio.run(scenario())


@pytest.mark.parametrize("trigger", ["focus", "ctrl+l"])
def test_returning_to_terminal_repaints_cached_images_after_tmux_window_switch(frames, trigger):
    from textual.events import AppFocus

    async def scenario():
        app = ImageHost()
        async with app.run_test(size=(80, 30)) as pilot:
            await pilot.pause()
            image = app.query_one(_WholeSixels)
            pixels = image._pixels
            frames.clear()
            if trigger == "focus":
                app.post_message(AppFocus())
            else:
                await pilot.press(trigger)
            await pilot.pause()
            assert graphic_frames(frames), 'returning to a tmux window must restore its cached bitmap'
            assert image._pixels is pixels, 'focus restoration must reuse decoded pixels'

    asyncio.run(scenario())
