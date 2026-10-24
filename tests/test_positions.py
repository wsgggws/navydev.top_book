"""The cursor, its encoding and the share codes."""

from __future__ import annotations

from lector.positions import (
    CROCKFORD_ALPHABET,
    Cursor,
    clamp_percent,
    decode_cursor,
    encode_cursor,
    generate_short_code,
    is_valid_short_code,
    normalize_short_code,
)


def test_cursor_round_trip():
    cursor = Cursor("b_9f3a2c1d", "c12", "c12.b3.s0", 4)
    assert decode_cursor(encode_cursor(cursor)) == cursor


def test_cursor_without_word_index():
    cursor = Cursor("b_1", "c0", "c0.b0.s0")
    assert decode_cursor(encode_cursor(cursor)) == cursor


def test_malformed_cursor_is_rejected():
    assert decode_cursor("nonsense") is None
    assert decode_cursor("a:b:c:z") is None
    assert decode_cursor(":b:c:") is None


def test_same_place_compares_every_field():
    one = Cursor("b", "c0", "c0.b0.s0", 1)
    assert one.same_place(Cursor("b", "c0", "c0.b0.s0", 1))
    assert not one.same_place(Cursor("b", "c0", "c0.b0.s0", 2))
    assert not one.same_place(None)


def test_short_codes_use_crockford_base32():
    for _ in range(50):
        code = generate_short_code()
        assert len(code) == 8
        assert all(char in CROCKFORD_ALPHABET for char in code)
        assert is_valid_short_code(code)


def test_short_code_normalisation_maps_excluded_letters():
    assert normalize_short_code("i1l0o0u") == "111000V"
    assert is_valid_short_code(normalize_short_code("iiiiiiii"))


def test_percent_is_clamped():
    assert clamp_percent(-1.0) == 0.0
    assert clamp_percent(2.0) == 1.0
    assert clamp_percent(0.5) == 0.5
