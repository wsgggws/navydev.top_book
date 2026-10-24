"""The book builder: Markdown → EPUB."""

from __future__ import annotations

import json

from lector.build import BuildError, find_source, markdown_to_html, read_source, write_epub
from lector.epub.parse import parse_epub


def test_markdown_headings_and_paragraphs():
    title, body, images = markdown_to_html("# 第一章\n\n一段正文。\n\n## 小节\n")
    assert title == "第一章"
    assert "<h1" in body
    assert "<h2>小节</h2>" in body
    assert "<p>一段正文。</p>" in body
    assert images == []


def test_markdown_lists_quotes_and_code():
    _, body, _ = markdown_to_html(
        "- 第一条\n- 第二条\n\n1. 一\n2. 二\n\n> 引用\n\n```\ncode()\n```\n"
    )
    assert "<ul><li>第一条</li><li>第二条</li></ul>" in body
    assert "<ol><li>一</li><li>二</li></ol>" in body
    assert "<blockquote><p>引用</p></blockquote>" in body
    assert "<pre>code()</pre>" in body


def test_markdown_inline_and_images():
    _, body, images = markdown_to_html(
        "**粗** *斜* `代码` [链接](http://x) ![图](images/a.jpg)\n"
    )
    assert "<strong>粗</strong>" in body
    assert "<em>斜</em>" in body
    assert "<code>代码</code>" in body
    assert '<a href="http://x">链接</a>' in body
    assert '<img src="images/a.jpg"' in body
    assert images == ["images/a.jpg"]


def test_markdown_escapes_html():
    _, body, _ = markdown_to_html("<script>alert(1)</script>\n")
    assert "<script>" not in body
    assert "&lt;script&gt;" in body


def test_build_a_book_from_a_directory(tmp_path):
    source = tmp_path / "some"
    source.mkdir()
    (source / "meta.json").write_text(
        json.dumps({"title": "测试书", "author": "作者", "language": "zh-CN"}),
        "utf-8",
    )
    (source / "01-开始.md").write_text("# 开始\n\n第一段。\n", "utf-8")
    (source / "02-之后.md").write_text("# 之后\n\n第二段。\n", "utf-8")

    book = read_source(source)
    assert book.title == "测试书"
    assert book.author == "作者"
    assert len(book.chapters) == 2
    assert book.chapters[0].title == "开始"

    target = tmp_path / "some.epub"
    write_epub(book, target, {})
    assert target.exists()

    parsed = parse_epub(target.read_bytes())
    assert parsed.title == "测试书"
    assert parsed.author == "作者"
    assert len(parsed.chapters) == 2
    assert parsed.sentence_count >= 2
    assert [node.title for node in parsed.toc] == ["开始", "之后"]
    # 每个目录节点都要指向真正存在的章节。
    chapter_ids = {chapter.id for chapter in parsed.chapters}
    assert all(node.chapter_id in chapter_ids for node in parsed.toc)


def test_build_from_a_single_file(tmp_path):
    path = tmp_path / "solo.md"
    path.write_text("# 一本书\n\n只有一章。\n", "utf-8")
    book = read_source(path)
    assert book.title == "一本书"
    assert len(book.chapters) == 1


def test_find_source_looks_next_to_the_target(tmp_path):
    (tmp_path / "some.md").write_text("# x\n", "utf-8")
    assert find_source(tmp_path / "some.epub").name == "some.md"
    with __import__("pytest").raises(BuildError):
        find_source(tmp_path / "missing.epub")


def test_cli_builds_without_importing(tmp_path, capsys):
    from lector.build import main

    (tmp_path / "some.md").write_text("# 一本书\n\n正文。\n", "utf-8")
    target = tmp_path / "some.epub"
    assert main([str(target), "--no-import"]) == 0
    assert target.exists()
    assert "已生成" in capsys.readouterr().out


def test_the_build_is_reproducible(tmp_path):
    """The same source always yields the same bytes.

    The content hash decides whether an upload is a duplicate, so a build that
    changed every time would fill the shelf with copies of the same book.
    """
    import hashlib

    source = tmp_path / "some.md"
    source.write_text("# 一本书\n\n正文。\n", "utf-8")
    book = read_source(source)
    first = tmp_path / "a.epub"
    second = tmp_path / "b.epub"
    write_epub(book, first, {})
    write_epub(book, second, {})
    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()  # noqa: E731
    assert digest(first) == digest(second)
