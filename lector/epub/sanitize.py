"""Markup whitelist.

Everything that reaches the browser passes through here.  The rules are a
whitelist, not a blacklist: an unknown tag is dropped, a known-dangerous tag is
dropped *with* its content, and an unknown attribute never survives.
"""

from __future__ import annotations

from collections.abc import Iterable

#: Tags whose content is inert for reading.  Kept so text survives.
ALLOWED_TAGS = frozenset(
    {
        "a", "abbr", "b", "blockquote", "br", "cite", "code", "dd", "del", "dfn",
        "div", "dl", "dt", "em", "figcaption", "figure", "h1", "h2", "h3", "h4",
        "h5", "h6", "hr", "i", "img", "ins", "li", "mark", "ol", "p", "pre", "q",
        "s", "samp", "section", "small", "span", "strong", "sub", "sup", "table",
        "tbody", "td", "tfoot", "th", "thead", "tr", "u", "ul", "var", "wbr",
    }
)

#: Dropped together with everything inside them.
DROPPED_TAGS = frozenset(
    {
        "applet", "audio", "base", "button", "canvas", "datalist", "embed",
        "fieldset", "form", "frame", "frameset", "head", "iframe", "input",
        "label", "link", "map", "math", "meta", "meter", "noscript", "object",
        "option", "output", "param", "picture", "portal", "progress", "script",
        "select", "slot", "source", "style", "svg", "template", "textarea",
        "title", "track", "video",
    }
)

#: Attributes that may survive, per contract.
ALLOWED_ATTRS = frozenset({"href", "src", "alt", "title", "lang", "dir", "class"})

#: Only ``epub-*`` classes are kept (contract).
CLASS_PREFIX = "epub-"

#: URL schemes that may appear in ``href``/``src``.
SAFE_SCHEMES = frozenset({"http", "https", "mailto", "tel", "ftp"})

#: Control characters are stripped before scheme detection: ``java\x00script:``
#: is a classic way to smuggle a scheme past a naive check.
_CONTROL_CHARS = "".join(chr(c) for c in range(0x21) if c != 0x20) + "\x7f"


def is_dropped_tag(tag: str) -> bool:
    """True when the tag and everything inside it must be discarded."""
    return tag in DROPPED_TAGS


def is_allowed_tag(tag: str) -> bool:
    """True when the tag may be rendered."""
    return tag in ALLOWED_TAGS


def is_safe_url(url: str) -> bool:
    """Reject ``javascript:``, ``data:`` and anything else outside the whitelist."""
    if url is None:
        return False
    candidate = url.strip()
    # Strip control characters and whitespace *inside* the scheme as well.
    candidate = "".join(ch for ch in candidate if ch not in _CONTROL_CHARS)
    if not candidate:
        return True
    scheme, sep, _ = candidate.partition(":")
    if not sep:
        return True  # relative URL
    # A colon inside a path is not a scheme (``a/b:c`` is relative).
    if "/" in scheme or "?" in scheme or "#" in scheme:
        return True
    if not scheme[0].isalpha():
        return False
    return scheme.lower() in SAFE_SCHEMES


def _filter_class(value: str) -> str:
    kept = [token for token in value.split() if token.startswith(CLASS_PREFIX)]
    return " ".join(kept)


def filter_attrs(tag: str, attrs: Iterable[tuple[str, str | None]]) -> list[tuple[str, str]]:
    """Return the attributes of ``tag`` that survive the whitelist."""
    kept: list[tuple[str, str]] = []
    for name, value in attrs:
        name = name.lower()
        if name not in ALLOWED_ATTRS:
            continue
        value = value or ""
        if name == "class":
            filtered = _filter_class(value)
            if filtered:
                kept.append((name, filtered))
            continue
        if name in ("href", "src") and not is_safe_url(value):
            continue
        kept.append((name, value))
    return kept
