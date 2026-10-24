"""EPUB → Book / Chapter / Block / Sentence.

This module owns the whole parse: it validates the archive, walks the
container and the package document, builds the table of contents and finally
turns every spine document into blocks of sentences.
"""

from __future__ import annotations

import hashlib
import io
import posixpath
import re
import zipfile
from urllib.parse import unquote
from dataclasses import dataclass, field

from lector.epub.container import read_container_path
from lector.epub.errors import EpubNotAZipError, EpubSecurityError, EpubStructureError
from lector.epub.html import RawBlock, extract_blocks
from lector.epub.opf import OpfPackage, parse_opf
from lector.epub.sentences import split_sentences, split_words
from lector.epub.toc import TocEntry, build_toc

#: Upper bound on the expanded size of an archive.
MAX_TOTAL_UNCOMPRESSED = 500 * 1024 * 1024

_ENCODING_RE = re.compile(rb"""encoding\s*=\s*["']([A-Za-z0-9_\-]+)["']""")


@dataclass
class ParsedSentence:
    """A sentence with its position inside the block text."""

    id: str
    text: str
    char_start: int
    char_end: int
    words: list[tuple[str, int, int]] = field(default_factory=list)

    @property
    def word_count(self) -> int:
        return len(self.words)


@dataclass
class ParsedBlock:
    """A block of a chapter."""

    id: str
    type: str
    sentences: list[ParsedSentence] = field(default_factory=list)
    anchor: str | None = None
    anchors: list[str] = field(default_factory=list)
    alt: str | None = None
    src: str | None = None

    @property
    def char_count(self) -> int:
        return sum(len(s.text) for s in self.sentences)


@dataclass
class ParsedChapter:
    """A chapter in spine order."""

    id: str
    index: int
    title: str
    blocks: list[ParsedBlock] = field(default_factory=list)

    @property
    def sentence_count(self) -> int:
        return sum(len(b.sentences) for b in self.blocks)

    @property
    def word_count(self) -> int:
        return sum(s.word_count for b in self.blocks for s in b.sentences)

    @property
    def char_count(self) -> int:
        return sum(b.char_count for b in self.blocks)


@dataclass
class ParsedTocNode:
    """A navigation node bound to a chapter."""

    id: str
    title: str
    chapter_id: str
    anchor: str | None = None
    children: list["ParsedTocNode"] = field(default_factory=list)


@dataclass
class ParsedBook:
    """The full result of parsing one EPUB."""

    title: str
    author: str | None
    language: str | None
    sha256: str
    size_bytes: int
    chapters: list[ParsedChapter] = field(default_factory=list)
    toc: list[ParsedTocNode] = field(default_factory=list)
    cover_path: str | None = None

    @property
    def sentence_count(self) -> int:
        return sum(c.sentence_count for c in self.chapters)

    @property
    def word_count(self) -> int:
        return sum(c.word_count for c in self.chapters)

    @property
    def char_count(self) -> int:
        return sum(c.char_count for c in self.chapters)


# ---------------------------------------------------------------------------
# archive safety
# ---------------------------------------------------------------------------


def validate_archive(zf: zipfile.ZipFile) -> None:
    """Reject archives that try to escape the extraction root or explode."""
    total_compressed = 0
    total_size = 0
    for info in zf.infolist():
        name = info.filename
        if name.startswith("/") or ".." in name.replace("\\", "/").split("/"):
            raise EpubSecurityError(
                "EPUB 结构不完整：包含路径穿越条目", {"entry": name}
            )
        mode = (info.external_attr >> 16) & 0o170000
        if mode == 0o120000:
            raise EpubSecurityError("EPUB 结构不完整：包含符号链接条目", {"entry": name})
        total_compressed += info.compress_size
        total_size += info.file_size
        if total_size > MAX_TOTAL_UNCOMPRESSED:
            raise EpubSecurityError("EPUB 结构不完整：解压后体积超出上限")
    if total_compressed > 0 and total_size / total_compressed > 200:
        raise EpubSecurityError(
            "EPUB 结构不完整：解压膨胀比异常",
            {"ratio": round(total_size / total_compressed, 1)},
        )


def open_archive(data: bytes) -> zipfile.ZipFile:
    """Open the uploaded bytes as a ZIP container."""
    if not data[:4] == b"PK\x03\x04" and not data[:2] == b"PK":
        raise EpubNotAZipError("文件不是 ZIP 容器（EPUB 必须是 zip 结构）")
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise EpubNotAZipError("文件不是 ZIP 容器（EPUB 必须是 zip 结构）") from exc
    validate_archive(zf)
    return zf


def decode_document(data: bytes) -> str:
    """Decode an XHTML document, honouring its XML encoding declaration."""
    match = _ENCODING_RE.search(data[:200])
    encoding = match.group(1).decode("ascii") if match else "utf-8"
    try:
        return data.decode(encoding, errors="replace")
    except LookupError:
        return data.decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# parsing
# ---------------------------------------------------------------------------


def _build_blocks(chapter_id: str, raw_blocks: list[RawBlock]) -> list[ParsedBlock]:
    """Give raw blocks their ids and split their text into sentences."""
    blocks: list[ParsedBlock] = []
    for index, raw in enumerate(raw_blocks):
        block_id = f"{chapter_id}.b{index}"
        anchors = list(dict.fromkeys(raw.anchors))
        block = ParsedBlock(
            id=block_id,
            type=raw.type,
            anchor=anchors[0] if anchors else None,
            anchors=anchors,
            alt=raw.alt,
            src=raw.src,
        )
        text = raw.text
        for sent_index, (start, end) in enumerate(split_sentences(text)):
            sentence_text = text[start:end]
            words = [
                (text[ws:we], ws - start, we - start)
                for ws, we in split_words(sentence_text)
            ]
            block.sentences.append(
                ParsedSentence(
                    id=f"{block_id}.s{sent_index}",
                    text=sentence_text,
                    char_start=start,
                    char_end=end,
                    words=words,
                )
            )
        blocks.append(block)
    return blocks


def _chapter_titles(
    package: OpfPackage, entries: list[TocEntry]
) -> dict[int, str]:
    """Map a spine index to the title the table of contents gives it."""
    titles: dict[int, str] = {}
    for entry in entries:
        item = package.item_by_href(entry.href)
        if item is None:
            continue
        index = package.chapter_index_of(item.item_id)
        if index is None or not entry.title:
            continue
        titles.setdefault(index, entry.title)
    return titles


def _resolve_toc(
    package: OpfPackage,
    entries: list[TocEntry],
    href_to_chapter: dict[str, int],
    default_chapter: str,
) -> list[ParsedTocNode]:
    """Bind navigation nodes to chapters and give them their own ids."""
    def walk(items: list[TocEntry], fallback: str, prefix: str) -> list[ParsedTocNode]:
        nodes: list[ParsedTocNode] = []
        last_chapter = fallback
        for position, entry in enumerate(items):
            index = href_to_chapter.get(unquote(entry.href))
            chapter_id = f"c{index}" if index is not None else last_chapter
            last_chapter = chapter_id
            node_id = f"{prefix}{position}"
            nodes.append(
                ParsedTocNode(
                    id=node_id,
                    title=entry.title,
                    chapter_id=chapter_id,
                    anchor=entry.anchor,
                    children=walk(entry.children, chapter_id, f"{node_id}."),
                )
            )
        return nodes

    return walk(entries, default_chapter, "t")


def parse_epub(data: bytes) -> ParsedBook:
    """Parse EPUB bytes into the content model."""
    sha256 = hashlib.sha256(data).hexdigest()
    zf = open_archive(data)
    with zf:
        names = set(zf.namelist())
        if "META-INF/container.xml" not in names:
            raise EpubStructureError(
                "EPUB 结构不完整：缺少 OPF 文件", {"missing": "META-INF/container.xml"}
            )
        opf_path = read_container_path(zf.read("META-INF/container.xml"))
        if opf_path not in names:
            raise EpubStructureError(
                "EPUB 结构不完整：缺少 OPF 文件", {"missing": opf_path}
            )
        package = parse_opf(zf.read(opf_path), opf_path)

        def read_member(href: str) -> bytes:
            path, _ = package.resolve(href)
            return zf.read(path)

        entries = build_toc(package, read_member)
        titles = _chapter_titles(package, entries)

        href_to_chapter: dict[str, int] = {}
        for index, item_id in enumerate(package.spine):
            item = package.manifest[item_id]
            href_to_chapter[unquote(item.href)] = index

        chapters: list[ParsedChapter] = []
        for index, item_id in enumerate(package.spine):
            item = package.manifest[item_id]
            chapter_id = f"c{index}"
            path, _ = package.resolve(item.href)
            if path not in names:
                continue
            document = decode_document(zf.read(path))
            raw_blocks = extract_blocks(document, posixpath.dirname(path))
            title = titles.get(index) or _guess_title(raw_blocks) or _stem(item.href)
            chapters.append(
                ParsedChapter(
                    id=chapter_id,
                    index=index,
                    title=title,
                    blocks=_build_blocks(chapter_id, raw_blocks),
                )
            )

        default_chapter = chapters[0].id if chapters else "c0"
        toc = _resolve_toc(package, entries, href_to_chapter, default_chapter)
        cover_path = _find_cover(package, names)
        return ParsedBook(
            title=package.title or _stem(opf_path),
            author=package.creator or None,
            language=package.language or None,
            sha256=sha256,
            size_bytes=len(data),
            chapters=chapters,
            toc=toc,
            cover_path=cover_path,
        )


def _guess_title(blocks: list[RawBlock]) -> str:
    """Use the first heading of a document as its chapter title."""
    for block in blocks:
        if block.type in ("h1", "h2", "h3"):
            text = block.text.strip()
            if text:
                return text
    return ""


def _stem(href: str) -> str:
    """A human readable name for a document path."""
    base = posixpath.basename(href)
    for suffix in (".xhtml", ".html", ".htm", ".xml"):
        if base.lower().endswith(suffix):
            base = base[: -len(suffix)]
            break
    return base.replace("_", " ").strip() or href


def _find_cover(package: OpfPackage, names: set[str]) -> str | None:
    """Locate the cover image inside the archive."""
    candidates: list[str] = []
    if package.cover_id and package.cover_id in package.manifest:
        candidates.append(package.manifest[package.cover_id].href)
    for item in package.manifest.values():
        if item.media_type.startswith("image/") and "cover" in item.href.lower():
            candidates.append(item.href)
    for href in candidates:
        path, _ = package.resolve(href)
        if path in names:
            return path
    return None
