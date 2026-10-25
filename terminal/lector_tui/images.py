"""Image rendering for the terminal client.

Modern terminals get native graphics through ``textual-image`` (Sixel or the
Kitty graphics protocol), which preserves far more detail than block art.
Terminals without graphics support fall back to true-colour half blocks.
"""

from __future__ import annotations

from io import BytesIO
from typing import Any

from PIL import Image, ImageDraw

from lector_tui.image_data import decode_image
from rich.style import Style
from rich.text import Text
from textual_image.renderable import (
    HalfcellImage,
    Image as AutoImage,
    UnicodeImage,
)


def placeholder_cover(width: int = 200, height: int = 300) -> bytes:
    """A neutral 2:3 cover used while the real image is loading."""
    image = Image.new("RGB", (width, height), "#2b2b2b")
    draw = ImageDraw.Draw(image)
    draw.rectangle((10, 10, width - 11, height - 11), outline="#555555", width=2)
    draw.line((40, height - 55, width - 40, height - 55), fill="#666666", width=3)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def render_terminal_image(
    data: bytes,
    *,
    width: int = 72,
    max_height: int = 36,
) -> Text | None:
    """Render image bytes as high-quality true-colour half blocks."""
    image = decode_image(data)
    if image is None:
        return None
    image = image.convert("RGB")
    image.thumbnail((max(1, width), max(2, max_height * 2)), Image.Resampling.LANCZOS)
    pixel_width, pixel_height = image.size
    pixels = image.load()
    result = Text()
    for y in range(0, pixel_height, 2):
        for x in range(pixel_width):
            top = pixels[x, y]
            bottom = pixels[x, min(y + 1, pixel_height - 1)]
            result.append(
                "▀",
                style=Style(
                    color=f"#{top[0]:02x}{top[1]:02x}{top[2]:02x}",
                    bgcolor=f"#{bottom[0]:02x}{bottom[1]:02x}{bottom[2]:02x}",
                ),
            )
        result.append("\n")
    return result


def render_chapter_image(data: bytes) -> Any | None:
    """Render an embedded image at full terminal resolution when possible.

    ``textual-image`` chooses Sixel, Kitty graphics, or a Unicode fallback when
    imported.  We keep our coloured half-block renderer for the latter because
    it gives markedly better results than plain Unicode blocks.
    """
    if AutoImage in (HalfcellImage, UnicodeImage):
        return render_terminal_image(data)
    image = decode_image(data)
    if image is None:
        return None
    return AutoImage(image, width="100%", height="auto")
