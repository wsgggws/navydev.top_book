"""Inline image previews for terminals.

Images are converted to half-block characters with RGB foreground/background
colours. This works in WezTerm, iTerm2, Kitty, Ghostty and any terminal with
true-colour support and needs no special image protocol.
"""

from __future__ import annotations

from io import BytesIO

from PIL import Image, UnidentifiedImageError
from rich.style import Style
from rich.text import Text


def render_terminal_image(
    data: bytes,
    *,
    width: int = 36,
    max_height: int = 16,
) -> Text | None:
    """Render image bytes as a compact block-coloured Rich Text."""
    try:
        image = Image.open(BytesIO(data))
        if image.width * image.height > 50_000_000:
            return None
        image.load()
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError):
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
