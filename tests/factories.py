"""Builders for the EPUB files the tests parse."""

from __future__ import annotations

import io
import zipfile

#: A one pixel JPEG, enough for the media endpoint to serve.
TINY_JPEG = bytes.fromhex(
    "ffd8ffe000104a46494600010100000100010000ffdb004300ffffffffffffffffffff"
    "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
    "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffc2000b08001000"
    "010103011100ffc40014000100000000000000000000000000000009ffda00080101000000"
    "3f00d2cf20ffd9"
)

CONTAINER = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="{opf}" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""

XHTML = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head><title>{title}</title></head>
<body>
{body}
</body>
</html>
"""


def _zip(members: dict[str, str | bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(zipfile.ZipInfo("mimetype"), b"application/epub+zip", compress_type=zipfile.ZIP_STORED)
        for name, payload in members.items():
            if isinstance(payload, bytes):
                zf.writestr(name, payload)
            else:
                zf.writestr(name, payload.encode("utf-8"))
    return buffer.getvalue()


def build_epub2(
    title: str = "测试书",
    author: str = "作者甲",
    language: str = "zh-CN",
    chapters: list[tuple[str, str]] | None = None,
) -> bytes:
    """An EPUB2 book with an NCX table of contents."""
    chapters = chapters or [
        ("第一章", "<h1>第一章</h1><p>他把玫瑰留在原处。风从远处来。</p>"),
        ("第二章", "<h1>第二章</h1><p>He left. She stayed. The price is 3.14 dollars.</p>"),
    ]
    manifest = []
    spine = []
    ncx_points = []
    for index, (name, body) in enumerate(chapters):
        item_id = f"ch{index}"
        href = f"text/{item_id}.html"
        manifest.append(
            f'<item id="{item_id}" href="{href}" media-type="application/xhtml+xml"/>'
        )
        spine.append(f'<itemref idref="{item_id}"/>')
        ncx_points.append(
            f"""
      <navPoint id="nav{index}" playOrder="{index + 1}">
        <navLabel><text>{name}</text></navLabel>
        <content src="{href}"/>
      </navPoint>"""
        )
    opf = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="uid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>{title}</dc:title>
    <dc:creator>{author}</dc:creator>
    <dc:language>{language}</dc:language>
    <dc:identifier id="uid">urn:uuid:test-0001</dc:identifier>
  </metadata>
  <manifest>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
    {''.join(manifest)}
  </manifest>
  <spine toc="ncx">{''.join(spine)}</spine>
</package>
"""
    ncx = f"""<?xml version="1.0" encoding="utf-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head><meta name="dtb:uid" content="test-0001"/></head>
  <docTitle><text>{title}</text></docTitle>
  <navMap>{''.join(ncx_points)}
  </navMap>
</ncx>
"""
    members: dict[str, str | bytes] = {
        "META-INF/container.xml": CONTAINER.format(opf="OEBPS/content.opf"),
        "OEBPS/content.opf": opf,
        "OEBPS/toc.ncx": ncx,
    }
    for index, (name, body) in enumerate(chapters):
        members[f"OEBPS/text/ch{index}.html"] = XHTML.format(title=name, body=body)
    members["OEBPS/text/images/f1.jpg"] = TINY_JPEG
    return _zip(members)


def build_epub3(
    title: str = "导航书",
    author: str = "作者乙",
    language: str = "zh-CN",
    chapters: list[tuple[str, str]] | None = None,
) -> bytes:
    """An EPUB3 book with a ``nav`` document."""
    chapters = chapters or [
        ("开始", "<h1>开始</h1><p>他说：“好。”然后走了。</p>"),
        ("之后", "<h1>之后</h1><p>Mr. Smith met Dr. Jones. He waited…</p>"),
    ]
    manifest = []
    spine = []
    nav_items = []
    for index, (name, body) in enumerate(chapters):
        item_id = f"ch{index}"
        href = f"text/{item_id}.html"
        manifest.append(
            f'<item id="{item_id}" href="{href}" media-type="application/xhtml+xml"/>'
        )
        spine.append(f'<itemref idref="{item_id}"/>')
        nav_items.append(
            f'<li><a href="{href}">{name}</a></li>'
        )
    opf = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>{title}</dc:title>
    <dc:creator>{author}</dc:creator>
    <dc:language>{language}</dc:language>
    <dc:identifier id="uid">urn:uuid:test-0002</dc:identifier>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    {''.join(manifest)}
  </manifest>
  <spine>{''.join(spine)}</spine>
</package>
"""
    nav = XHTML.format(
        title="目录",
        body=f'<nav epub:type="toc" id="toc"><ol>{"".join(nav_items)}</ol></nav>',
    )
    members: dict[str, str | bytes] = {
        "META-INF/container.xml": CONTAINER.format(opf="OEBPS/content.opf"),
        "OEBPS/content.opf": opf,
        "OEBPS/nav.xhtml": nav,
    }
    for index, (name, body) in enumerate(chapters):
        members[f"OEBPS/text/ch{index}.html"] = XHTML.format(title=name, body=body)
    return _zip(members)


def build_malicious_epub() -> bytes:
    """An EPUB with a path traversal entry, a script and a javascript link."""
    members: dict[str, str | bytes] = {
        "META-INF/container.xml": CONTAINER.format(opf="OEBPS/content.opf"),
        "OEBPS/content.opf": """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="uid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>恶意书</dc:title><dc:identifier id="uid">urn:uuid:evil</dc:identifier>
  </metadata>
  <manifest><item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
  <item id="c0" href="text/ch0.html" media-type="application/xhtml+xml"/></manifest>
  <spine toc="ncx"><itemref idref="c0"/></spine>
</package>
""",
        "OEBPS/toc.ncx": """<?xml version="1.0" encoding="utf-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head><meta name="dtb:uid" content="evil"/></head><docTitle><text>恶意书</text></docTitle>
  <navMap><navPoint id="n1"><navLabel><text>坏章</text></navLabel>
  <content src="text/ch0.html"/></navPoint></navMap></ncx>
""",
        "OEBPS/text/ch0.html": XHTML.format(
            title="坏章",
            body=(
                "<script>alert('xss')</script>"
                "<p onclick=\"alert(1)\">正文<script>bad()</script>继续</p>"
                "<a href=\"javascript:alert(1)\">点我</a>"
                "<img src=\"javascript:alert(1)\" alt=\"坏图\"/>"
                "<iframe src=\"http://evil\"></iframe>"
            ),
        ),
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(zipfile.ZipInfo("mimetype"), b"application/epub+zip", compress_type=zipfile.ZIP_STORED)
        for name, payload in members.items():
            zf.writestr(name, payload)
        # A path traversal entry — it must be rejected outright.
        zf.writestr("../../etc/passwd", b"root:x:0:0:root:/root:/bin/sh")
    return buffer.getvalue()


def build_epub_with_encoded_href() -> bytes:
    """A book whose document names contain spaces and are percent encoded."""
    body = "<h1>空格章</h1><p>正文在这里。</p>"
    xhtml = XHTML.format(title="空格章", body=body)
    opf = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="uid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>空格书</dc:title><dc:identifier id="uid">urn:uuid:space</dc:identifier>
  </metadata>
  <manifest><item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
  <item id="c0" href="text/ch%200.html" media-type="application/xhtml+xml"/></manifest>
  <spine toc="ncx"><itemref idref="c0"/></spine>
</package>
"""
    ncx = """<?xml version="1.0" encoding="utf-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <head><meta name="dtb:uid" content="space"/></head><docTitle><text>空格书</text></docTitle>
  <navMap><navPoint id="n1"><navLabel><text>空格章</text></navLabel>
  <content src="text/ch%200.html"/></navPoint></navMap></ncx>
"""
    members: dict[str, str | bytes] = {
        "META-INF/container.xml": CONTAINER.format(opf="OEBPS/content.opf"),
        "OEBPS/content.opf": opf,
        "OEBPS/toc.ncx": ncx,
        "OEBPS/text/ch 0.html": xhtml,
    }
    return _zip(members)
