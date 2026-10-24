"""The sentence splitting rules.

These tests are the contract of ``lector/epub/sentences.py``.
"""

from __future__ import annotations

import pytest

from lector.epub.sentences import split_sentences, split_words


def sentences(text: str) -> list[str]:
    """The sentences of a text, as strings."""
    return [text[start:end] for start, end in split_sentences(text)]


def test_chinese_terminators_end_a_sentence():
    assert sentences("他把玫瑰留在原处。风从远处来！") == [
        "他把玫瑰留在原处。",
        "风从远处来！",
    ]


def test_chinese_semicolon_ends_a_sentence():
    assert sentences("他走了；她来了；") == ["他走了；", "她来了；"]


def test_closing_quote_belongs_to_the_sentence():
    assert sentences("他说：“好。”然后走了。") == ["他说：“好。”", "然后走了。"]


def test_ellipsis_is_one_terminator():
    assert sentences("等等……他走了。") == ["等等……", "他走了。"]


def test_english_needs_whitespace_after_the_mark():
    assert sentences("He left. She stayed.") == ["He left. ", "She stayed."]
    assert sentences("Really?Yes!") == ["Really?Yes!"]


def test_english_closing_quote_ends_the_sentence():
    assert sentences('He said "Hi." Then left.') == ['He said "Hi." ', "Then left."]


def test_decimal_point_does_not_end_a_sentence():
    assert sentences("The price is 3.14 dollars. Really?") == [
        "The price is 3.14 dollars. ",
        "Really?",
    ]


@pytest.mark.parametrize(
    "text",
    [
        "Mr. Smith left.",
        "Dr. Jones arrived.",
        "See e.g. the appendix.",
        "That is etc. and more.",
    ],
)
def test_abbreviations_do_not_end_a_sentence(text: str):
    assert len(sentences(text)) == 1


def test_initial_is_not_a_sentence_end():
    assert sentences("J. R. R. Tolkien wrote it.") == ["J. R. R. Tolkien wrote it."]


def test_mixed_chinese_and_english():
    assert sentences("他说 Hello world。然后走了。") == ["他说 Hello world。", "然后走了。"]


def test_spans_tile_the_text():
    text = "第一句。Second one! 第三句？"
    spans = split_sentences(text)
    assert spans[0][0] == 0
    assert spans[-1][1] == len(text)
    for previous, following in zip(spans, spans[1:]):
        assert previous[1] == following[0]


def test_empty_text_has_no_sentences():
    assert split_sentences("") == []


def test_words_are_single_characters_in_chinese():
    assert split_words("他把玫瑰留在原处。") == [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 6), (6, 7), (7, 8)]


def test_words_are_runs_in_latin():
    assert split_words("He left.") == [(0, 2), (3, 7)]


def test_words_ignore_punctuation():
    assert split_words("Hi, there!") == [(0, 2), (4, 9)]
