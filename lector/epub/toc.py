"""Table of contents.

EPUB3 ships a ``nav`` document, EPUB2 an NCX file, and plenty of real books
ship only one of them.  Both parsers normalise into the same tree so the rest
of the system never has to care which one a book used.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from html.parser import HTMLParser

from lector.epub.container import find_all, local_name
from lector.epub.errors import EpubStructureError
from lector.epub.opf import OpfPackage


@dataclass
class TocEntry:
    """A navigation node before it is bound to a chapter."""

    title: str
    href: str
    anchor: str | None = None
    children: list["TocEntry"] = field(default_factory=list)


class _NavExtractor(HTMLParser):
    """Pull the structure out of an EPUB3 ``nav`` document."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root: list[dict] = []
        self._stack: list[list[dict]] = [self.root]
        self._items: list[dict] = []
        self._in_nav = False
        self._nav_depth = 0
        self._nav_is_toc = False
        self._seen_toc = False
        self._in_anchor = False
        self._href: str | None = None
        self._text: list[str] = []
        self._title_of_doc = ""

    # -- helpers ---------------------------------------------------------
    def _capture_text(self) -> None:
        if self._items and self._in_anchor:
            self._items[-1]["title"] += "".join(self._text)
        self._text = []

    # -- HTMLParser hooks ------------------------------------------------
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {k.lower(): (v or "") for k, v in attrs}
        if tag == "nav":
            self._in_nav = True
            self._nav_depth = 1
            kind = f"{attr.get('epub:type', '')} {attr.get('role', '')}".lower()
            self._nav_is_toc = "toc" in kind
            return
        if self._in_nav:
            self._nav_depth += 1
        if not self._in_nav:
            return
        if tag == "ol":
            # A nested list belongs to the item that encloses it; a top level
            # list continues the list we are already filling.
            target = self._items[-1]["children"] if self._items else self._stack[-1]
            self._stack.append(target)
        elif tag == "li":
            self._capture_text()
            self._items.append({"title": "", "href": None, "children": []})
        elif tag == "a":
            self._capture_text()
            self._in_anchor = True
            self._href = attr.get("href")
            self._text = []

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("br", "hr", "img"):
            return
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag == "nav":
            self._in_nav = False
            self._nav_depth = 0
            return
        if not self._in_nav:
            return
        self._nav_depth -= 1
        if tag == "a":
            self._capture_text()
            if self._items:
                self._items[-1]["href"] = self._href
            self._in_anchor = False
            self._href = None
        elif tag == "li":
            self._capture_text()
            if self._items:
                item = self._items.pop()
                self._stack[-1].append(item)
        elif tag == "ol":
            if len(self._stack) > 1:
                self._stack.pop()

    def handle_data(self, data: str) -> None:
        if self._in_nav and self._items:
            self._text.append(data)

    def entries(self) -> list[dict]:
        """Return the collected navigation items."""
        return self.root


def parse_nav(data: bytes) -> list[TocEntry]:
    """Parse an EPUB3 navigation document."""
    parser = _NavExtractor()
    try:
        parser.feed(data.decode("utf-8", errors="replace"))
        parser.close()
    except Exception as exc:  # noqa: BLE001 - a broken nav must not kill the book
        raise EpubStructureError("EPUB 结构不完整：nav 无法解析", {"reason": str(exc)}) from exc
    return _to_entries(parser.entries())


def _to_entries(items: list[dict]) -> list[TocEntry]:
    """Convert the nav extractor's dictionaries into :class:`TocEntry`."""
    entries: list[TocEntry] = []
    for item in items:
        href = item.get("href")
        if not href:
            continue
        title = " ".join((item.get("title") or "").split())
        anchor = None
        path = href
        if "#" in path:
            path, _, anchor = path.partition("#")
        entries.append(
            TocEntry(title=title, href=path, anchor=anchor or None, children=_to_entries(item["children"]))
        )
    return entries


def parse_ncx(data: bytes) -> list[TocEntry]:
    """Parse an EPUB2 NCX document."""
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise EpubStructureError("EPUB 结构不完整：NCX 无法解析", {"reason": str(exc)}) from exc
    nav_map = None
    for node in root.iter():
        if local_name(node.tag) == "navMap":
            nav_map = node
            break
    if nav_map is None:
        raise EpubStructureError("EPUB 结构不完整：NCX 缺少 navMap")
    return _ncx_points(nav_map)


def _ncx_points(parent: ET.Element) -> list[TocEntry]:
    entries: list[TocEntry] = []
    for node in find_all(parent, "navPoint"):
        label = ""
        for child in node:
            if local_name(child.tag) == "navLabel":
                label = " ".join("".join(child.itertext()).split())
                break
        href = ""
        anchor = None
        for child in node:
            if local_name(child.tag) == "content":
                href = child.get("src", "")
                break
        if "#" in href:
            href, _, anchor = href.partition("#")
        entries.append(
            TocEntry(
                title=label,
                href=href,
                anchor=anchor or None,
                children=_ncx_points(node),
            )
        )
    return entries


def find_ncx_item(package: OpfPackage):
    """Locate the NCX manifest item, preferring the one the spine points at."""
    if package.spine_toc and package.spine_toc in package.manifest:
        return package.manifest[package.spine_toc]
    for item in package.manifest.values():
        if item.media_type == "application/x-dtbncx+xml":
            return item
    for item in package.manifest.values():
        if item.href.lower().endswith(".ncx"):
            return item
    return None


def find_nav_item(package: OpfPackage):
    """Locate the EPUB3 navigation document."""
    for item in package.manifest.values():
        if item.is_navigation:
            return item
    for item in package.manifest.values():
        if item.media_type == "application/xhtml+xml" and item.href.lower().endswith((".nav.xhtml", ".toc.xhtml")):
            return item
    return None


def build_toc(package: OpfPackage, read_member) -> list[TocEntry]:
    """Build the table of contents, preferring EPUB3 ``nav`` over NCX."""
    nav_item = find_nav_item(package)
    if nav_item is not None:
        try:
            data = read_member(nav_item.href)
        except KeyError:
            data = None
        if data:
            entries = parse_nav(data)
            if entries:
                return entries
    ncx_item = find_ncx_item(package)
    if ncx_item is not None:
        data = read_member(ncx_item.href)
        entries = parse_ncx(data)
        if entries:
            return entries
    return []
