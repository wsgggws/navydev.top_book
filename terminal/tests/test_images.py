"""Inline terminal image rendering."""

from __future__ import annotations

import asyncio
from io import BytesIO

from PIL import Image


def test_image_is_rendered_as_colored_half_blocks():
    from lector_tui.images import render_terminal_image

    image = Image.new("RGB", (8, 8), "red")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    rendered = render_terminal_image(buffer.getvalue(), width=4, max_height=3)

    assert rendered is not None
    assert "▀" in rendered.plain
    assert rendered.spans


def test_invalid_image_is_ignored():
    from lector_tui.images import render_chapter_image, render_terminal_image

    assert render_terminal_image(b"not an image") is None
    assert render_chapter_image(b"not an image") is None


def test_chapter_image_uses_native_renderer_or_colour_fallback():
    from lector_tui.images import render_chapter_image

    image = Image.new("RGB", (40, 60), "blue")
    buffer = BytesIO()
    image.save(buffer, format="PNG")

    assert render_chapter_image(buffer.getvalue()) is not None


def test_chapter_image_widget_survives_highlight_updates():
    """Highlighting text must not rebuild the image widgets."""
    from textual.app import App, ComposeResult
    from textual.containers import VerticalScroll
    from lector_tui.image_widget import TerminalImage

    from lector_tui.screens.reader import ChapterText

    image = Image.new("RGB", (80, 120), "blue")
    buffer = BytesIO()
    image.save(buffer, format="PNG")

    class Host(App):
        def compose(self) -> ComposeResult:
            yield VerticalScroll(ChapterText())

    async def scenario() -> None:
        app = Host()
        async with app.run_test() as pilot:
            view = app.query_one(ChapterText)
            view.set_chapter({
                "title": "Test",
                "blocks": [
                    {
                        "type": "p",
                        "sentences": [
                            {"id": "s1", "text": "first"},
                            {"id": "s2", "text": "second"},
                        ],
                    },
                    {"type": "img", "id": "img1", "src": "x", "alt": "test"},
                ],
            })
            view.set_images({"img1": buffer.getvalue()})
            view.set_cursor("s1")
            await pilot.pause()

            image_widget = view.query_one(TerminalImage)
            view.set_cursor("s2")
            view.set_words([{"text": "second"}], 0)
            await pilot.pause()

            assert view.query_one(TerminalImage) is image_widget
            assert image_widget.image is not None

    asyncio.run(scenario())


def test_loading_images_preserves_paragraphs_and_initial_text():
    from textual.app import App, ComposeResult
    from textual.containers import VerticalScroll
    from lector_tui.screens.reader import ChapterText
    from lector_tui.image_widget import TerminalImage

    buffer = BytesIO()
    Image.new("RGB", (80, 120), "blue").save(buffer, format="PNG")

    class Host(App):
        def compose(self) -> ComposeResult:
            yield VerticalScroll(ChapterText())

    async def scenario():
        app = Host()
        async with app.run_test() as pilot:
            view = app.query_one(ChapterText)
            view.set_chapter({
                "title": "Test",
                "blocks": [
                    {"type": "p", "sentences": [{"id": "s1", "text": "First paragraph"}]},
                    {"type": "img", "id": "img", "src": "x"},
                    {"type": "p", "sentences": [{"id": "s2", "text": "Last paragraph"}]},
                ],
            })
            await pilot.pause()
            first = view.widget_for_sentence("s1")
            last = view.widget_for_sentence("s2")
            assert "First paragraph" in first.render().plain
            assert "Last paragraph" in last.render().plain
            widget = view.query_one(TerminalImage)
            view.set_images({"img": buffer.getvalue()})
            await pilot.pause()
            assert view.widget_for_sentence("s1") is first
            assert view.widget_for_sentence("s2") is last
            assert view.query_one(TerminalImage) is widget
            assert widget.display and widget.image is not None

    asyncio.run(scenario())


def test_tall_illustration_fits_the_preview_instead_of_cropping_its_bottom():
    from textual.app import App, ComposeResult
    from textual.containers import VerticalScroll
    from lector_tui.image_widget import TerminalImage

    class Host(App):
        CSS = ".chapter-image { width: 40; height: auto; }"

        def compose(self) -> ComposeResult:
            yield VerticalScroll(
                TerminalImage(
                    Image.new("RGB", (200, 2000), "blue"),
                    classes="chapter-image",
                )
            )

    async def scenario():
        app = Host()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            preview = app.query_one(TerminalImage)
            assert 0 < preview.size.height <= 16
            assert preview._get_styled_size() == ("auto", "auto")

    asyncio.run(scenario())
