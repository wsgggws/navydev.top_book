"""Image rendering for the terminal client.

Modern terminals get native graphics through ``textual-image`` (Sixel or the
Kitty graphics protocol), which preserves far more detail than block art.
Terminals without graphics support fall back to true-colour half blocks.
"""

from __future__ import annotations

from io import BytesIO
from typing import Any

from PIL import Image, ImageOps, UnidentifiedImageError
from rich.style import Style
from rich.text import Text
from textual_image.renderable import (
    HalfcellImage,
    Image as AutoImage,
    UnicodeImage,
)


def render_terminal_image(
    data: bytes,
    *,
    width: int = 72,
    max_height: int = 36,
) -> Text | None:
    """Render image bytes as high-quality true-colour half blocks."""
    try:
        image = Image.open(BytesIO(data))
        if image.width * image.height > 50_000_000:
            return None
        image.load()
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError):
        return None

    image = ImageOps.exif_transpose(image).convert("RGB")
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
    try:
        return AutoImage(BytesIO(data), width="100%", height="auto")
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError, ValueError):
        return None
