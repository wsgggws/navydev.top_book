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
    from textual_image.widget import Image as TerminalImage

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
            view.set_chapter(
                {
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
                }
            )
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
