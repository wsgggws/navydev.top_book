"""The EPUB parser."""

from __future__ import annotations

import zipfile

import pytest

from lector.epub.errors import EpubNotAZipError, EpubSecurityError, EpubStructureError
from lector.epub.parse import parse_epub


def test_epub2_metadata_and_toc(epub2_bytes: bytes):
    book = parse_epub(epub2_bytes)
    assert book.title == "测试书"
    assert book.author == "作者甲"
    assert book.language == "zh-CN"
    assert len(book.chapters) == 2
    assert [(node.title, node.chapter_id) for node in book.toc] == [
        ("第一章", "c0"),
        ("第二章", "c1"),
    ]


def test_epub3_nav_is_preferred(epub3_bytes: bytes):
    book = parse_epub(epub3_bytes)
    assert book.title == "导航书"
    assert [(node.title, node.chapter_id) for node in book.toc] == [
        ("开始", "c0"),
        ("之后", "c1"),
    ]


def test_ids_are_stable_and_predictable(epub2_bytes: bytes):
    first = parse_epub(epub2_bytes)
    second = parse_epub(epub2_bytes)
    ids_first = [block.id for chapter in first.chapters for block in chapter.blocks]
    ids_second = [block.id for chapter in second.chapters for block in chapter.blocks]
    assert ids_first == ids_second
    assert ids_first[0] == "c0.b0"
    sentence_ids = [
        sentence.id for chapter in first.chapters for block in chapter.blocks for sentence in block.sentences
    ]
    assert sentence_ids[0] == "c0.b0.s0"


def test_sentences_carry_character_ranges(epub2_bytes: bytes):
    book = parse_epub(epub2_bytes)
    chapter = book.chapters[1]
    block = chapter.blocks[1]
    text = "".join(sentence.text for sentence in block.sentences)
    for sentence in block.sentences:
        assert text[sentence.char_start : sentence.char_end] == sentence.text


def test_toc_node_ids_are_not_chapter_ids(epub2_bytes: bytes):
    book = parse_epub(epub2_bytes)
    for node in book.toc:
        assert node.id != node.chapter_id
        assert not node.id.startswith("c")


def test_non_zip_is_rejected():
    with pytest.raises(EpubNotAZipError):
        parse_epub(b"this is not a zip file at all")


def test_zip_without_container_is_rejected():
    import io

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("hello.txt", "hello")
    with pytest.raises(EpubStructureError):
        parse_epub(buffer.getvalue())


def test_path_traversal_entry_is_rejected(malicious_bytes: bytes):
    with pytest.raises(EpubSecurityError):
        parse_epub(malicious_bytes)


def test_script_and_javascript_are_sanitised(epub2_bytes: bytes):
    from lector.epub.html import extract_blocks

    html = (
        "<html><body><script>alert('xss')</script>"
        "<p>正文<script>bad()</script>继续</p>"
        '<a href="javascript:alert(1)">点我</a>'
        '<img src="javascript:alert(1)" alt="坏图"/>'
        "<iframe src=\"http://evil\"></iframe></body></html>"
    )
    blocks = extract_blocks(html, "OEBPS")
    text = " ".join(block.text for block in blocks)
    assert "alert" not in text
    assert "bad()" not in text
    assert "正文继续" in text
    assert not any(block.src for block in blocks if block.type == "img")


def test_image_src_is_resolved_into_the_epub(epub2_bytes: bytes):
    from lector.epub.html import extract_blocks

    blocks = extract_blocks('<div><img src="images/f1.jpg" alt="图"/></div>', "OEBPS/text")
    images = [block for block in blocks if block.type == "img"]
    assert len(images) == 1
    assert images[0].src == "OEBPS/text/images/f1.jpg"
    assert images[0].alt == "图"


def test_real_book_parses(real_epub_bytes: bytes):
    book = parse_epub(real_epub_bytes)
    assert book.title
    assert len(book.chapters) > 5
    assert book.sentence_count > 100
    assert book.toc
    assert len(book.toc) == len(book.chapters)
    # Every navigation node points at a chapter that exists.
    chapter_ids = {chapter.id for chapter in book.chapters}
    for node in book.toc:
        assert node.chapter_id in chapter_ids


def test_parsing_is_idempotent(real_epub_bytes: bytes):
    first = parse_epub(real_epub_bytes)
    second = parse_epub(real_epub_bytes)
    assert [c.id for c in first.chapters] == [c.id for c in second.chapters]
    assert first.sha256 == second.sha256


def test_percent_encoded_hrefs_resolve():
    """A document called ``ch 0.html`` is reachable through ``ch%200.html``."""
    from factories import build_epub_with_encoded_href

    book = parse_epub(build_epub_with_encoded_href())
    assert len(book.chapters) == 1
    assert book.chapters[0].sentence_count == 2
    # The directory entry must point at the chapter that really exists.
    assert book.toc[0].chapter_id == book.chapters[0].id


def test_anchors_on_headings_are_kept():
    """目录的落点常常挂在标题上，不只是 <a>。"""
    from lector.epub.html import extract_blocks

    blocks = extract_blocks(
        '<h1 id="epubw_com_id_5">第一章</h1><p>正文</p><span id="s1">行内</span>',
        "OEBPS",
    )
    anchors = [a for block in blocks for a in block.anchors]
    assert "epubw_com_id_5" in anchors
    assert "s1" in anchors
    # 锚点落在它所在的块上。
    heading = next(b for b in blocks if b.type == "h1")
    assert "epubw_com_id_5" in heading.anchors


def test_dropped_tags_do_not_carry_anchors():
    """被丢弃的标签不该留下锚点。"""
    from lector.epub.html import extract_blocks

    blocks = extract_blocks('<svg id="x"><script id="y"/></svg><p>正文</p>', "OEBPS")
    anchors = [a for block in blocks for a in block.anchors]
    assert "x" not in anchors
    assert "y" not in anchors
