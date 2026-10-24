"""Sentence and word segmentation for mixed Chinese/English text.

The rules are the contract of this module and are pinned by
``tests/test_sentence_split.py``:

* Chinese terminators ``。！？；…`` end a sentence, together with any closing
  quotes that trail them.
* English ``.!?`` end a sentence only when followed by whitespace or the end
  of the text; closing quotes may sit between the mark and that whitespace.
* Decimal points, abbreviations (``Mr.``, ``e.g.``) and single-letter initials
  never end a sentence.
* Whitespace belongs to the sentence it follows, so the spans of a block tile
  the block text exactly.
"""

from __future__ import annotations


#: Terminators that always end a sentence.
CJK_TERMINATORS = "。！？；…"

#: Terminators that end a sentence only in a trailing position.
ASCII_TERMINATORS = ".!?"

#: Closing marks that may trail a terminator.
CLOSING_CHARS = "”’」』）】》〉»\"')]}"

#: Tokens that never end a sentence.
ABBREVIATIONS = frozenset(
    {
        "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "mt", "rev", "hon",
        "gen", "col", "capt", "lt", "sgt", "maj", "gov", "sen", "rep",
        "vs", "etc", "al", "ca", "cf", "viz", "approx", "apt", "est", "fig",
        "figs", "no", "nos", "vol", "vols", "pp", "ed", "eds", "trans", "orig",
        "dept", "univ", "inc", "ltd", "co", "corp", "plc", "jan", "feb", "mar",
        "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec",
        "eg", "ie", "am", "pm", "ref", "refs", "ch", "sec", "art", "para",
    }
)


def _is_cjk_letter(ch: str) -> bool:
    """True for Han, Kana and Hangul letters — one of them is one word."""
    cp = ord(ch)
    return (
        0x3400 <= cp <= 0x4DBF
        or 0x4E00 <= cp <= 0x9FFF
        or 0xF900 <= cp <= 0xFAFF
        or 0x3040 <= cp <= 0x30FF
        or 0xAC00 <= cp <= 0xD7AF
    )


def _word_before(text: str, index: int) -> str:
    """The token that ends right before ``text[index]``."""
    end = index
    start = index
    while start > 0 and (text[start - 1].isalnum() or text[start - 1] in "._'"):
        start -= 1
    return text[start:end].rstrip(".")


def _is_abbreviation(token: str) -> bool:
    """True for abbreviations and initialisms such as ``e.g``, ``U.S.A``, ``J``."""
    if not token:
        return False
    lowered = token.lower()
    if lowered in ABBREVIATIONS:
        return True
    parts = lowered.split(".")
    if len(parts) >= 2 and all(len(part) <= 1 for part in parts[:-1]):
        return True
    # A lone capital letter is an initial: "J. R. R. Tolkien".
    return len(token) == 1 and token.isupper()


def _closes_sentence(text: str, index: int) -> bool:
    """True when the ASCII mark at ``index`` may end a sentence."""
    mark = text[index]
    nxt = index + 1
    if mark == ".":
        # Decimals ("3.14") and abbreviations ("Mr.", "e.g.") never end a
        # sentence, not even when a space follows them.
        prev = text[index - 1] if index > 0 else ""
        if prev.isdigit() and nxt < len(text) and text[nxt].isdigit():
            return False
        if _is_abbreviation(_word_before(text, index)):
            return False
    if nxt >= len(text):
        return True
    if text[nxt].isspace():
        return True
    if text[nxt] in CLOSING_CHARS:
        # "He said \"Hi.\"" — the quote closes the sentence, not the word.
        after = nxt
        while after < len(text) and text[after] in CLOSING_CHARS:
            after += 1
        return after >= len(text) or text[after].isspace()
    return False


def _absorb_trailing(text: str, index: int) -> int:
    """Extend ``index`` over closing marks and the whitespace that follows."""
    n = len(text)
    while index < n and text[index] in CLOSING_CHARS:
        index += 1
    while index < n and text[index].isspace():
        index += 1
    return index


def split_sentences(text: str) -> list[tuple[int, int]]:
    """Return ``(start, end)`` spans of every sentence in ``text``.

    Spans tile the string: the first starts at 0, the last ends at
    ``len(text)`` and consecutive spans share a boundary.  Trailing whitespace
    belongs to the sentence it follows.
    """
    spans: list[tuple[int, int]] = []
    n = len(text)
    start = 0
    i = 0
    while i < n:
        ch = text[i]
        if ch in CJK_TERMINATORS:
            end = i + 1
            while end < n and (text[end] in CJK_TERMINATORS or text[end] in CLOSING_CHARS):
                end += 1
            end = _absorb_trailing(text, end)
            if end > start:
                spans.append((start, end))
            start = end
            i = end
            continue
        if ch in ASCII_TERMINATORS and _closes_sentence(text, i):
            end = i + 1
            end = _absorb_trailing(text, end)
            if end > start:
                spans.append((start, end))
            start = end
            i = end
            continue
        i += 1
    if start < n:
        spans.append((start, n))
    return spans


def split_words(text: str) -> list[tuple[int, int]]:
    """Return ``(start, end)`` spans of every word in ``text``.

    A CJK letter is one word; a run of Latin letters or digits is one word.
    Punctuation and whitespace are separators and never form a word.
    """
    spans: list[tuple[int, int]] = []
    n = len(text)
    i = 0
    while i < n:
        ch = text[i]
        if _is_cjk_letter(ch):
            spans.append((i, i + 1))
            i += 1
            continue
        if ch.isalnum():
            j = i
            while j < n and text[j].isalnum() and not _is_cjk_letter(text[j]):
                j += 1
            spans.append((i, j))
            i = j
            continue
        i += 1
    return spans


def normalize_whitespace(text: str) -> str:
    """Collapse runs of whitespace into single spaces and strip the ends."""
    return " ".join(text.split())


def normalize_pre_whitespace(text: str) -> str:
    """Normalise whitespace inside a ``pre`` block without collapsing lines."""
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    return "\n".join(lines).strip("\n")


def align_boundaries(
    text: str,
    words: list[tuple[int, int]],
    boundaries: list[tuple[str, float, float]],
) -> list[tuple[str, float, float]]:
    """Map engine word boundaries onto the sentence's own word list.

    Engines report boundaries in their own tokenisation — Chinese often in
    multi-character chunks, English per word, punctuation usually dropped.
    This walks both sides together and hands back one timing per word of the
    sentence, interpolating inside a boundary that covers several words.
    """
    if not words or not boundaries:
        return []
    lowered = text.lower()
    spans: list[tuple[int, int, float, float]] = []
    cursor = 0
    for needle, start, end in boundaries:
        needle = needle.strip()
        if not needle:
            continue
        position = lowered.find(needle.lower(), cursor)
        if position < 0:
            position = lowered.find(needle.lower())
            if position < 0:
                continue
        spans.append((position, position + len(needle), start, end))
        cursor = position + len(needle)
    if not spans:
        return []
    aligned: list[tuple[str, float, float]] = []
    for word_start, word_end in words:
        span = next(
            (s for s in spans if s[0] < word_end and word_start < s[1]),
            None,
        )
        if span is None:
            # No engine boundary covers this word: borrow the nearest one.
            nearest = min(spans, key=lambda s: abs(s[0] - word_start))
            aligned.append((text[word_start:word_end], round(nearest[2], 3), round(nearest[3], 3)))
            continue
        span_start, span_end, time_start, time_end = span
        total = max(span_end - span_start, 1)
        duration = time_end - time_start
        begin = time_start + (word_start - span_start) / total * duration
        finish = time_start + (word_end - span_start) / total * duration
        aligned.append((text[word_start:word_end], round(begin, 3), round(finish, 3)))
    return aligned
