"""Inline terminal image rendering."""

from __future__ import annotations

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
