"""Bounded validation and decoding of untrusted EPUB image bytes."""

from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageOps


MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_IMAGE_DIMENSION = 16_000
MAX_IMAGE_PIXELS = 20_000_000
MAX_DECODED_BYTES = 80_000_000


def decode_image(data: bytes) -> Image.Image | None:
    """Return an owned RGBA first frame, or None for unsafe/invalid images.

    Check the container as well as the decoded pixels: Pillow's verify alone
    does not decode JPEGs, while load alone can accept a damaged PNG checksum.
    The caller owns the returned image and should close it when finished.
    """
    if not data or len(data) > MAX_IMAGE_BYTES:
        return None
    try:
        with Image.open(BytesIO(data)) as image:
            if not _safe_dimensions(image):
                return None
            image.verify()
        with Image.open(BytesIO(data)) as image:
            if not _safe_dimensions(image):
                return None
            image.load()
            return ImageOps.exif_transpose(image).convert("RGBA")
    except (
        OSError,
        ValueError,
        SyntaxError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ):
        return None


def _safe_dimensions(image: Image.Image) -> bool:
    # RGBA conversion and Pillow's RGB backing store both need four bytes per
    # pixel, including images whose encoded mode is palette or monochrome.
    pixels = image.width * image.height
    return (
        image.format in {"JPEG", "PNG", "GIF", "WEBP"}
        and image.width > 0
        and image.height > 0
        and max(image.size) <= MAX_IMAGE_DIMENSION
        and pixels <= MAX_IMAGE_PIXELS
        and pixels * 4 <= MAX_DECODED_BYTES
    )


def is_valid_image(data: bytes) -> bool:
    """Validate the same bytes renderers accept, releasing decoded storage."""
    image = decode_image(data)
    if image is None:
        return False
    image.close()
    return True
