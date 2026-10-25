"""Safe image decoding shared by downloads, cache, and renderers."""

from __future__ import annotations

from io import BytesIO
import warnings

from PIL import Image
import pytest

from lector_tui.image_data import decode_image, is_valid_image


def make_image(size: tuple[int, int] = (8, 8), format: str = "PNG") -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, "red").save(buffer, format=format)
    return buffer.getvalue()


@pytest.mark.parametrize("size", [(1, 16_001), (16_001, 1)])
def test_overlong_image_sides_are_rejected_even_with_few_pixels(size):
    data = make_image(size)
    assert decode_image(data) is None
    assert not is_valid_image(data)


@pytest.mark.parametrize("format", ["PNG", "JPEG", "GIF", "WEBP"])
def test_valid_images_return_independent_decoded_rgba_pixels(format):
    data = make_image(format=format)
    image = decode_image(data)
    assert image is not None
    try:
        assert image.size == (8, 8)
        assert image.mode == "RGBA"
        red, green, blue, alpha = image.getpixel((0, 0))
        assert red >= 250 and green <= 5 and blue <= 5 and alpha == 255
    finally:
        image.close()
    assert is_valid_image(data)


@pytest.mark.parametrize(
    ("limit", "value"),
    [("MAX_IMAGE_PIXELS", 63), ("MAX_DECODED_BYTES", 255), ("MAX_IMAGE_BYTES", 32)],
)
def test_independent_resource_budgets_are_enforced(monkeypatch, limit, value):
    monkeypatch.setattr(f"lector_tui.image_data.{limit}", value)
    assert decode_image(make_image()) is None


@pytest.mark.parametrize("size", [(1, 16_000), (16_000, 1)])
def test_maximum_side_length_is_allowed(size):
    assert is_valid_image(make_image(size))


def test_budgets_allow_the_exact_boundary(monkeypatch):
    data = make_image()
    monkeypatch.setattr("lector_tui.image_data.MAX_IMAGE_PIXELS", 64)
    monkeypatch.setattr("lector_tui.image_data.MAX_DECODED_BYTES", 256)
    monkeypatch.setattr("lector_tui.image_data.MAX_IMAGE_BYTES", len(data))
    assert is_valid_image(data)


@pytest.mark.parametrize("format", ["PNG", "JPEG"])
def test_truncated_images_are_rejected(format):
    assert decode_image(make_image(format=format)[:-12]) is None


def test_png_checksum_damage_is_rejected_even_when_pixels_can_decode():
    data = bytearray(make_image())
    checksum_start = data.index(b"IEND") - 8
    data[checksum_start] ^= 1
    assert decode_image(bytes(data)) is None


def test_pillow_bomb_warnings_promoted_to_errors_still_return_none(monkeypatch):
    data = make_image()
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 32)
    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        assert decode_image(data) is None


def test_other_image_formats_are_not_decoded():
    from io import BytesIO
    from PIL import Image
    from lector_tui.image_data import decode_image

    stream = BytesIO()
    Image.new("RGB", (4, 4)).save(stream, format="BMP")
    assert decode_image(stream.getvalue()) is None
