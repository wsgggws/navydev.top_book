"""Build an EPUB out of a book source.

The source is either a single Markdown file or a directory holding one
Markdown file per chapter::

    books/some/
        meta.json          # {"title": …, "author": …, "language": …}
        01-first.md
        02-second.md
        images/cover.jpg

The Markdown subset is deliberately small — headings, paragraphs, lists,
quotes, code, rules, images and the usual inline emphasis — because the
project does not want a Markdown dependency.
"""

from __future__ import annotations

import hashlib
import html
import io
import json
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

CONTAINER = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""

STYLE = """@charset "utf-8";
body { margin: 1em; line-height: 1.6; }
h1, h2, h3, h4, h5, h6 { line-height: 1.3; }
img { max-width: 100%; }
blockquote { margin-left: 2em; }
pre { white-space: pre-wrap; }
"""

XHTML = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="{lang}">
<head>
<title>{title}</title>
<link rel="stylesheet" type="text/css" href="style.css"/>
</head>
<body>
{body}
</body>
</html>
"""

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_RULE = re.compile(r"^(-{3,}|\*{3,}|_{3,})\s*$")
_QUOTE = re.compile(r"^>\s?(.*)$")
_LIST = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$")
_IMAGE_ONLY = re.compile(r"^!\[([^\]]*)\]\(([^)\s]+)\)\s*$")
_FENCE = re.compile(r"^```")


class BuildError(Exception):
    """The source cannot be turned into a book."""


@dataclass
class Chapter:
    """One chapter of the book."""

    title: str
    html: str
    images: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------


def escape(text: str) -> str:
    """Escape the characters that would otherwise become markup."""
    return html.escape(text, quote=False)


def inline(text: str) -> str:
    """The inline subset: code, bold, italic, images and links."""
    placeholders: list[str] = []

    def stash(markup: str) -> str:
        placeholders.append(markup)
        return f"\x00{len(placeholders) - 1}\x00"

    def code(match: re.Match[str]) -> str:
        return stash(f"<code>{escape(match.group(1))}</code>")

    def image(match: re.Match[str]) -> str:
        alt, src = match.group(1), match.group(2)
        return stash(f'<img src="{escape(src)}" alt="{escape(alt)}"/>')

    def link(match: re.Match[str]) -> str:
        label, href = match.group(1), match.group(2)
        return stash(f'<a href="{escape(href)}">{escape(label)}</a>')

    def bold(match: re.Match[str]) -> str:
        return stash(f"<strong>{match.group(1)}</strong>")

    def italic(match: re.Match[str]) -> str:
        return stash(f"<em>{match.group(1)}</em>")

    text = re.sub(r"`([^`]+)`", code, text)
    text = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)\)", image, text)
    text = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", link, text)
    text = re.sub(r"\*\*([^*]+)\*\*", bold, text)
    text = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", italic, text)

    def restore(match: re.Match[str]) -> str:
        return placeholders[int(match.group(1))]

    return re.sub(r"\x00(\d+)\x00", restore, text)


def markdown_to_html(text: str) -> tuple[str, str, list[str]]:
    """Markdown → ``(chapter title, body html, image paths)``."""
    lines = text.replace("\r\n", "\n").split("\n")
    out: list[str] = []
    images: list[str] = []
    title = ""
    index = 0
    total = len(lines)

    def collect_paragraph(start: int) -> tuple[list[str], int]:
        chunk: list[str] = []
        position = start
        while position < total and lines[position].strip():
            if position > start and (
                _HEADING.match(lines[position])
                or _RULE.match(lines[position])
                or _QUOTE.match(lines[position])
                or _LIST.match(lines[position])
                or _FENCE.match(lines[position])
            ):
                break
            chunk.append(lines[position].strip())
            position += 1
        return chunk, position

    while index < total:
        line = lines[index]
        stripped = line.strip()
        if not stripped:
            index += 1
            continue

        fence = _FENCE.match(stripped)
        if fence:
            index += 1
            code_lines: list[str] = []
            while index < total and not _FENCE.match(lines[index].strip()):
                code_lines.append(lines[index])
                index += 1
            index += 1
            out.append(f"<pre>{escape(chr(10).join(code_lines))}</pre>")
            continue

        heading = _HEADING.match(stripped)
        if heading:
            level = len(heading.group(1))
            text_value = heading.group(2).strip()
            if level == 1 and not title:
                title = text_value
                out.append(f'<h1 class="chapter-title">{inline(escape(text_value))}</h1>')
            else:
                out.append(f"<h{level}>{inline(escape(text_value))}</h{level}>")
            index += 1
            continue

        if _RULE.match(stripped):
            out.append("<hr/>")
            index += 1
            continue

        if _QUOTE.match(stripped):
            quote: list[str] = []
            while index < total and _QUOTE.match(lines[index].strip()):
                quote.append(_QUOTE.match(lines[index].strip()).group(1))
                index += 1
            out.append(f"<blockquote><p>{inline(escape(' '.join(quote)))}</p></blockquote>")
            continue

        if _LIST.match(stripped):
            ordered = bool(re.match(r"^\d", _LIST.match(stripped).group(2)))
            items: list[str] = []
            while index < total and _LIST.match(lines[index]):
                items.append(_LIST.match(lines[index]).group(3))
                index += 1
            tag = "ol" if ordered else "ul"
            body = "".join(f"<li>{inline(escape(item))}</li>" for item in items)
            out.append(f"<{tag}>{body}</{tag}>")
            continue

        if _IMAGE_ONLY.match(stripped):
            match = _IMAGE_ONLY.match(stripped)
            images.append(match.group(2))
            out.append(
                f'<figure><img src="{escape(match.group(2))}" '
                f'alt="{escape(match.group(1))}"/></figure>'
            )
            index += 1
            continue

        chunk, index = collect_paragraph(index)
        paragraph = " ".join(chunk)
        for found in re.findall(r"!\[[^\]]*\]\(([^)\s]+)\)", paragraph):
            images.append(found)
        out.append(f"<p>{inline(escape(paragraph))}</p>")

    return title, "\n".join(out), images


# ---------------------------------------------------------------------------
# 书的组装
# ---------------------------------------------------------------------------


@dataclass
class BookSource:
    """A book that is ready to be written out."""

    title: str
    author: str
    language: str
    chapters: list[Chapter]
    cover: bytes | None = None
    cover_name: str = "cover.jpg"


def read_source(path: Path) -> BookSource:
    """Read a Markdown file or a directory of chapters."""
    if path.is_dir():
        return _read_directory(path)
    if path.is_file():
        return _read_single(path)
    raise BuildError(f"找不到源文件：{path}")


def _read_directory(path: Path) -> BookSource:
    meta: dict = {}
    meta_path = path / "meta.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text("utf-8"))
    chapter_files = sorted(
        [p for p in path.glob("*.md")] + [p for p in path.glob("*.markdown")],
        key=lambda p: p.name,
    )
    if not chapter_files:
        raise BuildError(f"{path} 里没有 Markdown 章节")
    chapters: list[Chapter] = []
    for chapter_file in chapter_files:
        title, body, images = markdown_to_html(chapter_file.read_text("utf-8"))
        chapters.append(
            Chapter(title=title or chapter_file.stem, html=body, images=images)
        )
    title = meta.get("title") or chapters[0].title or path.name
    cover = None
    cover_name = "cover.jpg"
    cover_meta = meta.get("cover")
    if cover_meta:
        cover_path = path / cover_meta
        if cover_path.exists():
            cover = cover_path.read_bytes()
            cover_name = Path(cover_meta).name
    return BookSource(
        title=title,
        author=meta.get("author", ""),
        language=meta.get("language", "zh-CN"),
        chapters=chapters,
        cover=cover,
        cover_name=cover_name,
    )


def _read_single(path: Path) -> BookSource:
    title, body, images = markdown_to_html(path.read_text("utf-8"))
    return BookSource(
        title=title or path.stem,
        author="",
        language="zh-CN",
        chapters=[Chapter(title=title or path.stem, html=body, images=images)],
    )


def collect_images(source: BookSource, root: Path) -> dict[str, bytes]:
    """Read the images the chapters refer to."""
    found: dict[str, bytes] = {}
    for chapter in source.chapters:
        for name in chapter.images:
            if name.startswith("http://") or name.startswith("https://"):
                continue
            candidate = (root / name) if root.is_dir() else (root.parent / name)
            if candidate.exists() and candidate.is_file():
                found[Path(name).name] = candidate.read_bytes()
    return found


#: zip 里的时间戳固定下来，同样的源才能生成同样的字节。
FIXED_TIME = (1980, 1, 1, 0, 0, 0)


def _entry(name: str) -> zipfile.ZipInfo:
    """A zip entry with a fixed timestamp."""
    info = zipfile.ZipInfo(name, date_time=FIXED_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    return info


def identifier_for(source: BookSource) -> str:
    """A stable identifier for the book.

    It has to be stable: the content hash decides whether an upload is a
    duplicate, so the same source must always produce the same bytes.
    """
    digest = hashlib.sha256()
    digest.update(source.title.encode("utf-8"))
    digest.update(source.author.encode("utf-8"))
    digest.update(source.language.encode("utf-8"))
    for chapter in source.chapters:
        digest.update(chapter.title.encode("utf-8"))
        digest.update(chapter.html.encode("utf-8"))
    return digest.hexdigest()[:32]


def write_epub(source: BookSource, target: Path, images: dict[str, bytes]) -> Path:
    """Write the book out as an EPUB.

    The output is byte-for-byte reproducible: the same source always yields the
    same file, so uploading it twice is recognised as the same book.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        info = zipfile.ZipInfo("mimetype", date_time=FIXED_TIME)
        info.compress_type = zipfile.ZIP_STORED
        zf.writestr(info, b"application/epub+zip")
        zf.writestr(_entry("META-INF/container.xml"), CONTAINER)
        zf.writestr(_entry("OEBPS/style.css"), STYLE)
        for name, payload in images.items():
            zf.writestr(_entry(f"OEBPS/images/{name}"), payload)
        if source.cover:
            zf.writestr(_entry(f"OEBPS/{source.cover_name}"), source.cover)

        manifest = []
        spine = []
        nav_points = []
        for index, chapter in enumerate(source.chapters):
            name = f"ch{index}.xhtml"
            manifest.append(
                f'<item id="ch{index}" href="{name}" media-type="application/xhtml+xml"/>'
            )
            spine.append(f'<itemref idref="ch{index}"/>')
            nav_points.append(
                f"""
    <navPoint id="nav{index}" playOrder="{index + 1}">
      <navLabel><text>{html.escape(chapter.title)}</text></navLabel>
      <content src="{name}"/>
    </navPoint>"""
            )
            zf.writestr(
                _entry(f"OEBPS/{name}"),
                XHTML.format(
                    lang=source.language,
                    title=html.escape(chapter.title),
                    body=chapter.html,
                ),
            )

        cover_item = ""
        if source.cover:
            cover_item = (
                f'<item id="cover" href="{source.cover_name}" media-type="image/jpeg"/>'
            )
        opf = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="uid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>{html.escape(source.title)}</dc:title>
    <dc:creator>{html.escape(source.author)}</dc:creator>
    <dc:language>{html.escape(source.language)}</dc:language>
    <dc:identifier id="uid">urn:uuid:{identifier_for(source)}</dc:identifier>
    <meta name="cover" content="cover"/>
  </metadata>
  <manifest>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
    <item id="css" href="style.css" media-type="text/css"/>
    {cover_item}
    {''.join(manifest)}
  </manifest>
  <spine toc="ncx">{''.join(spine)}</spine>
</package>
"""
        zf.writestr(_entry("OEBPS/content.opf"), opf)
        ncx = f"""<?xml version="1.0" encoding="utf-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head><meta name="dtb:uid" content="lector"/></head>
  <docTitle><text>{html.escape(source.title)}</text></docTitle>
  <navMap>{''.join(nav_points)}
  </navMap>
</ncx>
"""
        zf.writestr(_entry("OEBPS/toc.ncx"), ncx)

    target.write_bytes(buffer.getvalue())
    return target


# ---------------------------------------------------------------------------
# 命令行
# ---------------------------------------------------------------------------


def find_source(target: Path) -> Path | None:
    """Where the sources of ``target`` live.

    ``books/some.epub`` is built from ``books/some.md`` or ``books/some/``.
    ``None`` means there is no source — the file itself may already exist and
    only needs to go into the library.
    """
    stem = target.with_suffix("")
    for candidate in (stem.with_suffix(".md"), stem):
        if candidate.exists():
            return candidate
    return None


def upload(path: Path, base_url: str, token: str = "") -> dict | None:
    """把生成的书送到服务端，让网页端立刻能看能听。"""
    import urllib.error
    import urllib.request
    import uuid

    boundary = f"----lector{uuid.uuid4().hex}"
    payload = path.read_bytes()
    head = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
        "Content-Type: application/epub+zip\r\n\r\n"
    ).encode("utf-8")
    body = head + payload + f"\r\n--{boundary}--\r\n".encode("utf-8")
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/v1/books", data=body, headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            import json as _json

            return _json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise BuildError(f"上传失败：HTTP {exc.code} {exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise BuildError(f"连不上服务端 {base_url}：{exc.reason}") from exc


def main(argv: list[str] | None = None) -> int:
    """``uv run python -m lector.build books/some.epub``"""
    import argparse
    import os

    parser = argparse.ArgumentParser(description="生成一本 EPUB")
    parser.add_argument("target", help="要生成的文件，例如 books/some.epub")
    parser.add_argument("--source", default=None, help="源文件或目录（默认按 target 推断）")
    parser.add_argument("--url", default=os.environ.get("LECTOR_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--token", default=os.environ.get("LECTOR_TOKEN", ""))
    parser.add_argument("--no-import", action="store_true", help="只生成，不送进服务端")
    parser.add_argument(
        "--import-only", action="store_true", help="不生成，只把已有的 EPUB 送进服务端"
    )
    args = parser.parse_args(argv)

    target = Path(args.target)
    source = Path(args.source) if args.source else find_source(target)

    if args.import_only:
        pass
    elif source is not None:
        book = read_source(source)
        root = source if source.is_dir() else source.parent
        images = collect_images(book, root)
        write_epub(book, target, images)
        print(
            f"已生成 {target}（{book.title}，{len(book.chapters)} 章，"
            f"{target.stat().st_size // 1024} KB）"
        )
    elif target.exists():
        # 没有源，只有成品：那就直接送进书架。
        print(f"{target} 已存在，直接送进书架")
    else:
        stem = target.with_suffix("")
        raise BuildError(
            f"找不到 {target}，也没有它的源文件。\n"
            f"  · 要造一本：先写 {stem.with_suffix('.md')} 或建目录 {stem}/\n"
            f"  · 要加一本现成的：把 .epub 放到那个位置再试"
        )

    if args.no_import:
        return 0
    if not target.exists():
        raise BuildError(f"没有可上传的文件：{target}")
    try:
        payload = upload(target, args.url, args.token)
    except BuildError as exc:
        print(f"未送进服务端：{exc}")
        print("起服务后再跑一次即可：make import")
        return 0
    book_id = payload["book"]["book_id"]
    duplicate = payload.get("duplicate")
    print(
        f"{'已在书架上' if duplicate else '已加入书架'}：{book_id}"
        f"  → {args.url}/?book={book_id}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
