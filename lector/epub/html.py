"""XHTML → block structure.

``html.parser`` gives us a token stream, not a DOM, so the extractor keeps a
small stack of frames instead of building a tree.  The result is a flat list of
blocks — paragraphs, headings, list items, images, rules — each carrying its
plain text and the anchors that point into it.

Only the innermost container may hold loose text at any moment: starting a
block or a nested container flushes it first, which keeps the emitted blocks in
document order.
"""

from __future__ import annotations

import posixpath
from dataclasses import dataclass, field
from urllib.parse import unquote
from html.parser import HTMLParser

from lector.epub import sanitize
from lector.epub.sentences import normalize_pre_whitespace, normalize_whitespace

#: Tags that become a block of their own.
TEXT_BLOCKS = {
    "p": "p",
    "h1": "h1",
    "h2": "h2",
    "h3": "h3",
    "h4": "h4",
    "h5": "h5",
    "h6": "h6",
    "li": "li",
    "blockquote": "blockquote",
    "pre": "pre",
}

#: Tags that only group content; loose text inside them becomes a paragraph.
CONTAINERS = {
    "div", "section", "article", "main", "header", "footer", "aside", "nav",
    "body", "html", "figure", "table", "thead", "tbody", "tfoot", "tr",
    "colgroup", "col", "caption", "address", "center", "font", "group",
    "dir", "menu", "details", "summary", "fieldset", "legend", "output",
    "dialog", "canvas", "picture", "map", "object", "embed", "iframe",
}


@dataclass
class RawBlock:
    """A block before it receives an id."""

    type: str
    parts: list[str] = field(default_factory=list)
    anchors: list[str] = field(default_factory=list)
    alt: str | None = None
    src: str | None = None

    @property
    def text(self) -> str:
        return "".join(self.parts)


class _Extractor(HTMLParser):
    """Turns an XHTML document into a flat list of :class:`RawBlock`."""

    def __init__(self, base_dir: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_dir = base_dir
        self.blocks: list[RawBlock] = []
        self._stack: list[dict] = []
        self._pending_anchors: list[str] = []
        self._skip: list[str] = []

    # -- block plumbing --------------------------------------------------
    def _target(self) -> dict | None:
        """The frame that currently receives text."""
        for frame in reversed(self._stack):
            if frame["kind"] in ("block", "container"):
                return frame
        return None

    def _new_block(self, block_type: str) -> RawBlock:
        block = RawBlock(type=block_type, anchors=self._pending_anchors)
        self._pending_anchors = []
        self.blocks.append(block)
        return block

    def _flush_block(self, frame: dict) -> None:
        """Emit the text collected in a block frame as its own block."""
        text = "".join(frame["parts"])
        frame["parts"] = []
        if not text.strip():
            return
        if frame["block_type"] == "pre":
            text = normalize_pre_whitespace(text)
        else:
            text = normalize_whitespace(text)
        if not text:
            return
        block = RawBlock(type=frame["block_type"], parts=[text], anchors=list(frame["anchors"]))
        frame["anchors"] = []
        self.blocks.append(block)

    def _flush_loose(self, frame: dict) -> None:
        """Emit the loose text of a container as a paragraph."""
        text = "".join(frame["parts"])
        frame["parts"] = []
        if not text.strip():
            return
        block = RawBlock(
            type="p", parts=[normalize_whitespace(text)], anchors=self._pending_anchors
        )
        self._pending_anchors = []
        self.blocks.append(block)

    # -- HTMLParser hooks ------------------------------------------------
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._skip:
            if tag == self._skip[-1]:
                self._skip.append(tag)
            return
        if sanitize.is_dropped_tag(tag):
            self._skip.append(tag)
            return

        if tag == "img":
            self._handle_img(attrs)
            return
        if tag == "hr":
            self._flush_current()
            self._new_block("hr")
            return
        if tag == "br":
            target = self._target()
            if target is not None:
                target["parts"].append("\n")
            return
        if tag == "a":
            anchor = attrs_value(attrs, "id") or attrs_value(attrs, "name")
            if anchor:
                self._record_anchor(anchor)
            return
        if tag in TEXT_BLOCKS:
            self._flush_current()
            frame = {
                "kind": "block",
                "tag": tag,
                "parts": [],
                "anchors": self._pending_anchors,
                "block_type": TEXT_BLOCKS[tag],
            }
            self._pending_anchors = []
            self._stack.append(frame)
            return
        if tag in CONTAINERS:
            self._flush_current()
            self._stack.append(
                {"kind": "container", "tag": tag, "parts": [], "anchors": []}
            )
            return
        # Inline and unknown tags: the text flows through untouched.

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("br", "hr", "img"):
            self.handle_starttag(tag, attrs)
            return
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if self._skip:
            if tag == self._skip[-1]:
                self._skip.pop()
            return
        frame = self._pop_frame(tag)
        if frame is None:
            return
        if frame["kind"] == "block":
            self._flush_block(frame)
        else:
            self._flush_loose(frame)

    def handle_data(self, data: str) -> None:
        if self._skip or not data:
            return
        target = self._target()
        if target is None:
            self._stack.append(
                {"kind": "container", "tag": "#root", "parts": [], "anchors": []}
            )
            target = self._stack[-1]
        target["parts"].append(data)

    # -- helpers ---------------------------------------------------------
    def _flush_current(self) -> None:
        """Finish the text that is pending before a new block starts."""
        for frame in reversed(self._stack):
            if frame["kind"] == "block":
                self._flush_block(frame)
                break
            if frame["kind"] == "container":
                self._flush_loose(frame)
                break

    def _record_anchor(self, anchor: str) -> None:
        target = self._target()
        if target is not None and target["kind"] == "block":
            target["anchors"].append(anchor)
            return
        self._pending_anchors.append(anchor)

    def _handle_img(self, attrs: list[tuple[str, str | None]]) -> None:
        clean = dict(sanitize.filter_attrs("img", attrs))
        src = clean.get("src")
        if not src:
            return
        resolved = self._resolve_src(src)
        if not resolved:
            return
        self._flush_current()
        block = self._new_block("img")
        block.src = resolved
        block.alt = clean.get("alt")

    def _resolve_src(self, src: str) -> str | None:
        """Resolve an image path against the document, keeping EPUB-internal ones."""
        if "://" in src or src.startswith("//") or src.startswith("data:"):
            return None
        path = unquote(src.split("#", 1)[0])
        if not path:
            return None
        if path.startswith("/"):
            return posixpath.normpath(path.lstrip("/"))
        return posixpath.normpath(posixpath.join(self.base_dir, path))

    def _pop_frame(self, tag: str) -> dict | None:
        for index in range(len(self._stack) - 1, -1, -1):
            if self._stack[index].get("tag") == tag:
                frame = self._stack[index]
                del self._stack[index:]
                return frame
        return None


def attrs_value(attrs: list[tuple[str, str | None]], name: str) -> str | None:
    """Read an attribute straight from the parser, bypassing the whitelist."""
    for key, value in attrs:
        if key.lower() == name:
            return value
    return None


def extract_blocks(xhtml: str, base_dir: str) -> list[RawBlock]:
    """Parse an XHTML document into blocks."""
    extractor = _Extractor(base_dir)
    extractor.feed(xhtml)
    extractor.close()
    # Close whatever the document left open.
    while extractor._stack:
        frame = extractor._stack.pop()
        if frame["kind"] == "block":
            extractor._flush_block(frame)
        else:
            extractor._flush_loose(frame)
    return extractor.blocks
