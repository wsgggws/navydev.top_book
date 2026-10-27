"""Reader geometry, reading chapter identity and display-only indentation."""

import asyncio
from types import SimpleNamespace

import pytest
from rich.cells import cell_len
from rich.console import Console
from rich.style import Style
from textual.geometry import Region
from textual.widgets import Static

from lector_tui.app import LectorApp
from lector_tui.image_app import ImageApp
from lector_tui.screens.reader import ChapterBlock, ChapterText, ListenScreen, ReaderScreen


@pytest.fixture
def reader_app(monkeypatch, tmp_path):
    monkeypatch.setenv("LECTOR_PROGRESS_FILE", str(tmp_path / "progress.json"))
    monkeypatch.setattr(ListenScreen, "start_playback", lambda self: None)
    chapters = {
        f"c{i}": {
            "chapter_id": f"c{i}", "title": f"Chapter {i}", "sentence_count": 1,
            "blocks": [{"type": "p", "sentences": [{"id": f"c{i}.s0", "text": "正文 mixed text " * 600}]}],
        }
        for i in range(4)
    }

    class Host(ImageApp):
        CSS = LectorApp.CSS
        BINDINGS = [("f", "toggle_fullscreen")]

        def __init__(self, screen_type=ReaderScreen, *, short=False):
            super().__init__()
            if short:
                chapters["c0"]["blocks"][0]["sentences"][0]["text"] = "Short 正文"
            self.reader = screen_type("layout-book")
            self.api = SimpleNamespace(
                base_url="https://example.test",
                get_book=lambda _: {"book": {"chapter_count": 4}},
                get_toc=lambda _: [
                    {"chapter_id": "c0", "title": "First", "children": [
                        {"chapter_id": "c1", "title": "Nested"},
                        {"chapter_id": "c1", "title": "Same chapter", "anchor": "part"},
                    ]},
                    {"chapter_id": "c2", "title": "Last"},
                ],
                get_chapter=lambda _, chapter_id: {"chapter": chapters[chapter_id]},
                percent=lambda *args: 0,
                search=lambda *args: {"results": [{"chapter_id": "c2", "sentence_id": "c2.s0", "snippet": "found"}]},
            )
            self.audio = SimpleNamespace(rate=1.0, backend="test", stop=lambda: None)

        def on_mount(self):
            self.push_screen(self.reader)

        def action_toggle_fullscreen(self):
            self.reader.toggle_fullscreen()

    return Host


@pytest.mark.parametrize("screen_type", [ReaderScreen, ListenScreen])
@pytest.mark.parametrize("short", [True, False], ids=["without-scrollbar", "with-scrollbar"])
def test_page_is_centered_in_remaining_area_after_resize_and_fullscreen(reader_app, screen_type, short):
    async def scenario():
        app = reader_app(screen_type, short=short)
        async with app.run_test(size=(180, 50)) as pilot:
            for width, height in [(180, 50), (100, 30), (48, 18), (80, 24), (180, 50)]:
                await pilot.resize_terminal(width, height)
                for fullscreen in [False, True]:
                    if app.reader.has_class("fullscreen") != fullscreen:
                        await pilot.press("f")
                    await pilot.pause()
                    toc = app.reader.query_one("#toc-pane")
                    area = app.reader.query_one("#text-area").content_region
                    pane = app.reader.query_one("#text-pane")
                    assert pane.show_vertical_scrollbar is (not short)
                    assert area.x == toc.region.right
                    assert toc.region.width <= min(30, int(width * .4))
                    assert abs((pane.region.x - area.x) - (area.right - pane.region.right)) <= 1
                    assert area.contains_region(pane.region)
                    # Include the scrollbar gutter when checking actual text margins.
                    body = app.reader.query_one(ChapterText).region
                    assert abs((body.x - area.x) - (area.right - body.right)) <= 1
                    if fullscreen:
                        assert pane.region.width == area.width
                        assert pane.region.height == area.height
                    else:
                        assert pane.region.width <= 96
                        assert pane.region.height <= 34

    asyncio.run(scenario())


@pytest.mark.parametrize("resume", [False, True])
@pytest.mark.parametrize("screen_type", [ReaderScreen, ListenScreen])
def test_reading_chapter_stays_marked_while_browsing_and_tracks_navigation(reader_app, resume, screen_type):
    async def scenario():
        app = reader_app(screen_type)
        if resume:
            app.reader.progress.set("layout-book", "c1", "c1.s0")
        async with app.run_test() as pilot:
            await pilot.pause()
            reader = app.reader
            toc = reader.query_one("#toc-pane")

            def marked():
                rows = list(toc.children)
                for row in rows:
                    assert ("●" in row.query_one(Static).render().plain) == row.has_class("toc-current")
                return [index for index, row in enumerate(rows) if row.has_class("toc-current")]

            assert marked() == ([1, 2] if resume else [0])
            await pilot.press("t")
            toc.index = 3
            await pilot.press("k")
            assert toc.index == 2
            assert marked() == ([1, 2] if resume else [0])
            toc.index = 3
            await pilot.press("enter")
            assert reader.chapter["chapter_id"] == "c2"
            assert marked() == [3]
            await pilot.press("ctrl+w", "bracketleft")
            assert marked() == [1, 2]
            reader.goto_hit({"chapter_id": "c0", "sentence_id": "c0.s0"})
            assert marked() == [0]
            reader.run_search("found")
            await pilot.pause()
            reader.goto_hit(reader._hits[0])
            reader.restore_toc()
            await pilot.pause()
            assert marked() == [3]
            reader.load_chapter("c3")  # Spine chapter absent from the TOC.
            assert marked() == []

    asyncio.run(scenario())


@pytest.mark.parametrize("body", ["中文段落测试自动换行。" * 5, "Alpha beta gamma delta " * 5], ids=["Chinese", "English"])
def test_only_first_paragraph_line_is_indented_and_word_spans_keep_offsets(body):
    view = ChapterText()
    sentence = {"id": "s0", "text": body}
    block = ChapterBlock(view, [{"type": "p", "sentences": [sentence]}], "p")
    rendered = block.build()
    assert rendered.plain == "    " + body + "\n"
    assert cell_len(rendered.plain) - cell_len(body + "\n") == 4
    lines = rendered.wrap(Console(), 24)
    assert lines[0].plain.startswith("    ")
    assert all(not line.plain.startswith("    ") for line in lines[1:] if line.plain.strip())

    # A later sentence in the paragraph must not receive another indent.
    tail = {"id": "s1", "text": "Tail 后一句"}
    block.blocks[0]["sentences"].append(tail)
    view.current_sentence = "s1"
    view.words = [{"text": "Tail"}, {"text": "后一句"}]
    view.word_index = 1
    block._style = lambda name: Style(reverse=True) if name == "word-now" else Style()
    highlighted = block.build()
    assert highlighted.plain == "    " + body + tail["text"] + "\n"
    span = next(span for span in highlighted.spans if span.style.reverse)
    assert highlighted.plain[span.start:span.end] == "后一句"
    assert span.start == 4 + len(body) + len("Tail ")
    assert sentence["text"] == body


@pytest.mark.parametrize("kind", ["h1", "h2", "h3", "li", "hr", "blockquote", "pre"])
def test_non_paragraph_blocks_do_not_get_a_paragraph_indent(kind):
    block = ChapterBlock(ChapterText(), [{"type": kind, "sentences": [{"id": "s0", "text": "Title"}]}], kind)
    assert not block.build().plain.startswith("    ")


def test_listening_highlight_keeps_paragraph_widget_and_cursor_visible_after_wrap(reader_app):
    async def scenario():
        app = reader_app(ListenScreen)
        async with app.run_test(size=(64, 20)) as pilot:
            await pilot.pause()
            view = app.reader.query_one(ChapterText)
            widget = view.widget_for_sentence("c0.s0")
            view.set_words([{"text": "正文"}], 0)
            app.reader.scroll_to_cursor()
            await pilot.pause()
            assert view.widget_for_sentence("c0.s0") is widget
            strips = widget.render_lines(Region(0, 0, widget.size.width, 1))
            assert strips[0].text.startswith("    正文")
            reversed_text = "".join(segment.text for strip in strips for segment in strip if segment.style and segment.style.reverse)
            assert reversed_text == "正文"
            pane = app.reader.query_one("#text-pane")
            assert pane.scrollable_content_region.overlaps(widget.region)

    asyncio.run(scenario())
