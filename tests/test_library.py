"""Repository filename metadata."""

from __future__ import annotations

from pathlib import Path

from lector.library import metadata_from_filename


def test_ascii_parentheses_split_title_and_author():
    assert metadata_from_filename(Path("Same as Ever (Morgan Housel).epub")) == (
        "Same as Ever",
        "Morgan Housel",
    )


def test_full_width_parentheses_split_title_and_author():
    assert metadata_from_filename(Path("病隙碎笔（史铁生）.epub")) == (
        "病隙碎笔",
        "史铁生",
    )


def test_author_may_contain_commas():
    assert metadata_from_filename(
        Path("Metaphors We Live By (George Lakoff, Mark Johnson).epub")
    ) == ("Metaphors We Live By", "George Lakoff, Mark Johnson")


def test_filename_without_author_keeps_the_whole_stem():
    assert metadata_from_filename(Path("红楼梦.epub")) == ("红楼梦", "")
