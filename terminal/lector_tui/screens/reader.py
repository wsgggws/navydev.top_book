"""Screen two — reading, and screen three — listening.

Both screens show the same blocks and sentences; the listening screen adds the
audio panel and the word highlight.  They share the position, so switching
between them never loses the place.
"""

from __future__ import annotations

from io import BytesIO

from rich.style import Style
from rich.text import Text
from textual_image.widget import Image as TerminalImage

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.events import Key
from textual.widgets import Footer, Input, ListItem, ListView, Static

from lector_tui.cache import ImageCache
from lector_tui.config import ProgressStore
from lector_tui.widgets import ImageScroll, VimListView

#: How many columns the directory takes.
TOC_WIDTH = 30


def flatten_toc(nodes: list[dict], depth: int = 0) -> list[tuple[dict, int]]:
    """The navigation tree as a flat list, keeping the depth."""
    flat: list[tuple[dict, int]] = []
    for node in nodes:
        flat.append((node, depth))
        flat.extend(flatten_toc(node.get("children", []), depth + 1))
    return flat


def word_offsets(sentence_text: str, words: list[dict]) -> list[tuple[int, int, dict]]:
    """Where every word sits inside the sentence.

    The server reports the words of a sentence in order, so the sentence text
    can be walked to find where each word starts.
    """
    offsets: list[tuple[int, int, dict]] = []
    cursor = 0
    for word in words:
        text = word.get("text", "")
        if not text:
            continue
        index = sentence_text.find(text, cursor)
        if index < 0:
            continue
        offsets.append((index, index + len(text), word))
        cursor = index + len(text)
    return offsets


class ChapterBlock(Static):
    """One paragraph, heading, rule or list group from a chapter."""

    COMPONENT_CLASSES = {
        "chapter-title",
        "sentence-current",
        "word-read",
        "word-now",
    }

    def __init__(self, chapter: "ChapterText", blocks: list[dict], kind: str) -> None:
        super().__init__(classes="chapter-block")
        self.chapter_view = chapter
        self.blocks = blocks
        self.kind = kind

    def refresh_content(self) -> None:
        self.update(self.build())

    def _style(self, name: str) -> Style:
        try:
            return self.get_component_styles(name).rich_style
        except Exception:  # noqa: BLE001 - a missing class must not break the text
            return Style()

    def build(self) -> Text:
        """Render this block with the current sentence and word highlight."""
        text = Text()
        if self.kind == "hr":
            return Text("─" * 40 + "\n")
        current_style = self._style("sentence-current")
        read_style = self._style("word-read")
        now_style = self._style("word-now")
        for block in self.blocks:
            if block.get("type") == "li":
                for sentence in block.get("sentences", []):
                    text.append("  • ", style=Style(dim=True))
                    if sentence["id"] == self.chapter_view.current_sentence:
                        self.chapter_view._append_sentence(
                            text, sentence, current_style, read_style, now_style
                        )
                    else:
                        text.append(sentence["text"])
                continue
            heading = (
                Style(bold=True)
                if block.get("type", "p").startswith("h")
                else Style()
            )
            for sentence in block.get("sentences", []):
                if sentence["id"] == self.chapter_view.current_sentence:
                    self.chapter_view._append_sentence(
                        text, sentence, current_style, read_style, now_style
                    )
                else:
                    text.append(sentence["text"], style=heading)
        text.append("\n")
        return text


class ChapterText(Vertical):
    """The current chapter, built from text blocks and native image widgets."""

    def __init__(self) -> None:
        super().__init__(classes="chapter-text")
        self.chapter: dict | None = None
        self.current_sentence: str | None = None
        self.words: list[dict] = []
        self.word_index: int = -1
        self.images: dict[str, bytes] = {}
        self._sentence_widgets: dict[str, ChapterBlock] = {}

    def compose(self) -> ComposeResult:
        self._sentence_widgets = {}
        if not self.chapter:
            return
        yield Static(
            self.chapter.get("title", ""),
            classes="chapter-title chapter-title-block",
        )
        blocks = self._blocks()
        index = 0
        while index < len(blocks):
            block = blocks[index]
            block_type = str(block.get("type", "p"))
            if block_type == "img":
                with Vertical(classes="chapter-image-block"):
                    data = self.images.get(str(block.get("id", "")))
                    if data:
                        yield TerminalImage(
                            image=BytesIO(data),
                            classes="chapter-image",
                        )
                    else:
                        yield Static(
                            "图片加载中…",
                            classes="chapter-image-loading",
                        )
                    if block.get("alt"):
                        yield Static(
                            f"图：{block['alt']}",
                            classes="chapter-image-caption",
                        )
                index += 1
                continue
            if block_type == "li":
                group = []
                while index < len(blocks) and blocks[index].get("type") == "li":
                    group.append(blocks[index])
                    index += 1
                yield self._make_text_widget(group, "li")
                continue
            elif block_type == "hr":
                widget = self._make_text_widget([block], "hr")
            else:
                widget = self._make_text_widget([block], block_type)
            yield widget
            index += 1

    def _blocks(self) -> list[dict]:
        return self._without_repeated_title()

    def _make_text_widget(self, blocks: list[dict], kind: str) -> ChapterBlock:
        widget = ChapterBlock(self, blocks, kind)
        for block in blocks:
            for sentence in block.get("sentences", []):
                self._sentence_widgets[str(sentence["id"])] = widget
        return widget

    def set_chapter(self, chapter: dict) -> None:
        self.chapter = chapter
        self.images = {}
        self.refresh(recompose=True)

    def set_images(self, images: dict[str, bytes]) -> None:
        self.images = images
        self.refresh(recompose=True)

    def set_cursor(self, sentence_id: str) -> None:
        previous = self.current_sentence
        self.current_sentence = sentence_id
        self.words = []
        self.word_index = -1
        for key in {previous, sentence_id}:
            if key:
                self._refresh_sentence(key)

    def set_words(self, words: list[dict], word_index: int) -> None:
        self.words = words
        self.word_index = word_index
        if self.current_sentence:
            self._refresh_sentence(self.current_sentence)

    def _refresh_sentence(self, sentence_id: str) -> None:
        widget = self._sentence_widgets.get(sentence_id)
        if widget is not None:
            widget.refresh_content()

    def widget_for_sentence(self, sentence_id: str) -> ChapterBlock | None:
        """The text widget that owns a sentence."""
        return self._sentence_widgets.get(sentence_id)

    def _without_repeated_title(self) -> list[dict]:
        """The chapter title is already on top — do not repeat it."""
        blocks = list(self.chapter.get("blocks", [])) if self.chapter else []
        if not blocks:
            return blocks
        first = blocks[0]
        if not str(first.get("type", "")).startswith("h"):
            return blocks
        text = "".join(
            sentence.get("text", "") for sentence in first.get("sentences", [])
        ).strip()
        title = str((self.chapter or {}).get("title", "")).strip()
        if text and text != title:
            return blocks
        return blocks[1:]

    def _append_sentence(
        self,
        text: Text,
        sentence: dict,
        current_style: Style,
        read_style: Style,
        now_style: Style,
    ) -> None:
        """The current sentence, with the word highlight when listening."""
        body = sentence["text"]
        if not self.words:
            text.append(body, style=current_style)
            return
        offsets = word_offsets(body, self.words)
        if not offsets:
            text.append(body, style=current_style)
            return
        cursor = 0
        for position, (start, end, _word) in enumerate(offsets):
            if start > cursor:
                text.append(body[cursor:start], style=current_style)
            if position == self.word_index:
                text.append(body[start:end], style=now_style)
            elif position < self.word_index:
                text.append(body[start:end], style=read_style)
            else:
                text.append(body[start:end], style=current_style)
            cursor = end
        if cursor < len(body):
            text.append(body[cursor:], style=current_style)


class BaseReaderScreen(Screen):
    """Shared behaviour of the reading and the listening screen."""

    BINDINGS = [
        # vim 的方向键：h/l 换句，j/k 滚行
        Binding("h", "previous_sentence", "上一句"),
        Binding("l", "next_sentence", "下一句"),
        Binding("j", "scroll_down", "下滚一行"),
        Binding("k", "scroll_up", "上滚一行"),
        Binding("left", "previous_sentence", "上一句"),
        Binding("right", "next_sentence", "下一句"),
        Binding("down", "scroll_down", "下滚一行"),
        Binding("up", "scroll_up", "上滚一行"),
        # vim 的翻页
        Binding("ctrl+d", "half_page_down", "下半页"),
        Binding("ctrl+u", "half_page_up", "上半页"),
        Binding("ctrl+f", "page_down", "下翻一页"),
        Binding("ctrl+b", "page_up", "上翻一页"),
        Binding("pagedown", "page_down", "下翻一页"),
        Binding("pageup", "page_up", "上翻一页"),
        Binding("ctrl+e", "scroll_down", "下滚一行"),
        Binding("ctrl+y", "scroll_up", "上滚一行"),
        Binding("H", "screen_top", "屏幕顶"),
        Binding("M", "screen_middle", "屏幕中"),
        Binding("L", "screen_bottom", "屏幕底"),
        Binding("z", "center", "居中"),
        # vim 的跳转
        Binding("g", "chapter_start", "章首"),
        Binding("bracketleft", "previous_chapter", "上一章"),
        Binding("bracketright", "next_chapter", "下一章"),
        Binding("G", "chapter_end", "章末"),
        Binding("home", "chapter_start", "章首"),
        Binding("end", "chapter_end", "章末"),
        # vim 的搜索
        Binding("slash", "search", "搜索"),
        Binding("n", "next_hit", "下一处"),
        Binding("N", "previous_hit", "上一处"),
        # 其余
        Binding("tab", "focus_toc", "目录"),
        Binding("t", "focus_toc", "目录"),
        Binding("ctrl+w", "switch_pane", "切换窗格"),
        Binding("q", "back", "返回"),
    ]

    def __init__(self, book_id: str) -> None:
        super().__init__()
        self.book_id = book_id
        self.book: dict | None = None
        self.chapter: dict | None = None
        self.chapter_ids: list[str] = []
        self.toc: list[dict] = []
        self.toc_flat: list[tuple[dict, int]] = []
        self.sentences: list[dict] = []
        self.sentence_index = 0
        self.cursor: dict | None = None
        self.progress = ProgressStore.load()
        self._percent_timer = None
        self._hits: list[dict] = []
        self._hit_index = -1
        self._pane_mode = "toc"
        self._image_store = ImageCache()

    # -- layout ----------------------------------------------------------
    def compose(self) -> ComposeResult:
        with Vertical():
            with Horizontal(id="reader-body"):
                yield VimListView(id="toc-pane")
                with Vertical(id="text-area"):
                    yield ImageScroll(ChapterText(), id="text-pane")
            yield Input(placeholder="搜索全书…（回车确认，Esc 取消）", id="search-input")
            yield Static("", id="status-bar")
            yield Footer()

    def on_mount(self) -> None:
        self.query_one("#search-input").display = False
        # 焦点默认在正文：h/j/k/l 是读的时候最常用的键。
        # 按 Tab 切到目录，目录里 j/k/l 才是目录自己的键。
        self.query_one("#text-pane", VerticalScroll).focus()
        self.load_book()

    # -- data ------------------------------------------------------------
    def load_book(self) -> None:
        """Load the book, its directory and the chapter the reader was in."""
        try:
            detail = self.app.api.get_book(self.book_id)
        except Exception as exc:  # noqa: BLE001
            self.notify(f"无法打开书籍：{exc}", title="错误", severity="error")
            return
        self.book = detail["book"]
        self.toc = self.app.api.get_toc(self.book_id)
        self.toc_flat = flatten_toc(self.toc)
        self.chapter_ids = sorted(
            {node["chapter_id"] for node in self.toc if node.get("chapter_id")}
        ) or [f"c{index}" for index in range(self.book.get("chapter_count", 0))]
        self.render_toc()
        # 位置只认本地这一份：终端与网页各记各的，互不影响。
        cursor = self.progress.get(self.book_id)
        chapter_id = cursor["chapter_id"] if cursor else None
        if chapter_id is None:
            chapter_id = self.first_readable_chapter()
        self.load_chapter(chapter_id, cursor["sentence_id"] if cursor else None)

    def first_readable_chapter(self) -> str:
        """Skip the cover and copyright pages that carry no words."""
        for chapter_id in self.chapter_ids[:6]:
            try:
                payload = self.app.api.get_chapter(self.book_id, chapter_id)
            except Exception:  # noqa: BLE001
                continue
            if payload["chapter"].get("sentence_count"):
                return chapter_id
        return self.chapter_ids[0] if self.chapter_ids else "c0"

    def render_toc(self) -> None:
        listing = self.query_one("#toc-pane", VimListView)
        listing.clear()
        for node, depth in self.toc_flat:
            title = node.get("title", "")
            marker = "  " * min(depth, 3)
            listing.append(ListItem(Static(f"{marker}{title}")))

    def load_chapter(self, chapter_id: str, sentence_id: str | None = None) -> None:
        """Load a chapter and put the cursor where it belongs."""
        try:
            payload = self.app.api.get_chapter(self.book_id, chapter_id)
        except Exception as exc:  # noqa: BLE001
            self.notify(f"无法加载章节：{exc}", title="错误", severity="error")
            return
        self.chapter = payload["chapter"]
        self.sentences = [
            sentence
            for block in self.chapter.get("blocks", [])
            for sentence in block.get("sentences", [])
        ]
        index = 0
        if sentence_id:
            for position, sentence in enumerate(self.sentences):
                if sentence["id"] == sentence_id:
                    index = position
                    break
        self.sentence_index = index
        self.query_one(ChapterText).set_chapter(self.chapter)
        self.set_cursor(index)
        self.load_chapter_images(chapter_id)
        self.update_status()

    def load_chapter_images(self, chapter_id: str) -> None:
        """Load image previews without blocking the terminal UI."""
        blocks = [
            block
            for block in (self.chapter or {}).get("blocks", [])
            if block.get("type") == "img" and block.get("src")
        ]
        if not blocks:
            return

        def worker() -> None:
            previews: dict[str, bytes] = {}
            for block in blocks:
                src = str(block["src"])
                cache_name = f"media:{src}"
                data = self._image_store.get(self.book_id, cache_name)
                if data is None:
                    try:
                        data = self.app.api.fetch_media(self.book_id, src)
                    except Exception:  # noqa: BLE001 - one bad image cannot break reading
                        data = None
                    if data is not None:
                        self._image_store.put(self.book_id, cache_name, data)
                if data is not None:
                    previews[str(block["id"])] = data
            try:
                self.app.call_from_thread(self._apply_chapter_images, chapter_id, previews)
            except Exception:  # noqa: BLE001 - the screen may already be closed
                pass

        self.run_worker(worker, group="chapter-images", exclusive=True, thread=True)

    def _apply_chapter_images(self, chapter_id: str, previews: dict[str, bytes]) -> None:
        if not self.chapter or self.chapter.get("chapter_id") != chapter_id:
            return
        try:
            self.query_one(ChapterText).set_images(previews)
            self.scroll_to_cursor()
        except Exception:  # noqa: BLE001 - the screen may already be closed
            pass

    # -- cursor ----------------------------------------------------------
    @property
    def current_sentence(self) -> dict | None:
        if not self.sentences:
            return None
        index = min(max(self.sentence_index, 0), len(self.sentences) - 1)
        return self.sentences[index]

    def set_cursor(self, index: int, *, scroll: bool = True) -> None:
        """Move the one cursor."""
        if not self.sentences:
            return
        self.sentence_index = min(max(index, 0), len(self.sentences) - 1)
        sentence = self.sentences[self.sentence_index]
        self.cursor = {
            "book_id": self.book_id,
            "chapter_id": self.chapter["chapter_id"],
            "sentence_id": sentence["id"],
            "word_index": None,
        }
        self.query_one(ChapterText).set_cursor(sentence["id"])
        if scroll:
            self.scroll_to_cursor()
        self.update_status()
        self.remember_position()
        self.schedule_percent()

    def scroll_to_cursor(self, center: bool = False, retry: bool = True) -> None:
        """Keep the current sentence visible, including after images."""
        pane = self.query_one("#text-pane", VerticalScroll)
        sentence = self.current_sentence
        if sentence is None:
            return
        widget = self.query_one(ChapterText).widget_for_sentence(sentence["id"])
        if widget is None:
            if retry:
                self.call_after_refresh(self.scroll_to_cursor, center, False)
            return
        pane.scroll_to_widget(widget, animate=False, center=center)

    def update_status(self) -> None:
        """The status line at the bottom."""
        total = len(self.sentences)
        current = self.sentence_index + 1
        percent = int((current / total * 100) if total else 0)
        chapter_title = self.chapter.get("title", "") if self.chapter else ""
        self.query_one("#status-bar", Static).update(
            f" {chapter_title} · {percent}% · 句 {current}/{total} · "
            "Space/p 播放 · q 返回"
        )

    # -- actions ---------------------------------------------------------
    # -- 滚动与定位 ------------------------------------------------------
    def action_scroll_down(self) -> None:
        """One line down, the way vim scrolls."""
        self.query_one("#text-pane", VerticalScroll).scroll_down(animate=False)

    def action_scroll_up(self) -> None:
        """One line up."""
        self.query_one("#text-pane", VerticalScroll).scroll_up(animate=False)

    def action_half_page_down(self) -> None:
        """Ctrl+d — half a page down."""
        self._scroll_by(self._page_size() // 2)

    def action_half_page_up(self) -> None:
        """Ctrl+u — half a page up."""
        self._scroll_by(-(self._page_size() // 2))

    def action_page_down(self) -> None:
        """Ctrl+f — a full page down."""
        self._scroll_by(self._page_size())

    def action_page_up(self) -> None:
        """Ctrl+b — a full page up."""
        self._scroll_by(-self._page_size())

    def _scroll_by(self, lines: int) -> None:
        """Scroll the text pane by a number of lines."""
        pane = self.query_one("#text-pane", VerticalScroll)
        target = pane.scroll_offset.y + lines
        pane.scroll_to(y=max(0, min(pane.max_scroll_y, target)), animate=False)

    def _page_size(self) -> int:
        """How many lines fit on the page."""
        try:
            return max(1, self.query_one("#text-pane", VerticalScroll).size.height)
        except Exception:  # noqa: BLE001
            return 20

    def action_screen_top(self) -> None:
        self.query_one("#text-pane", VerticalScroll).scroll_to(y=0, animate=False)

    def action_screen_bottom(self) -> None:
        pane = self.query_one("#text-pane", VerticalScroll)
        pane.scroll_to(y=pane.max_scroll_y, animate=False)

    def action_screen_middle(self) -> None:
        pane = self.query_one("#text-pane", VerticalScroll)
        pane.scroll_to(y=max(0, pane.max_scroll_y // 2), animate=False)

    def action_center(self) -> None:
        """Put the current sentence in the middle of the page."""
        self.scroll_to_cursor(center=True)

    def action_switch_pane(self) -> None:
        """Move the focus between the directory and the text."""
        toc = self.query_one("#toc-pane", VimListView)
        if toc.has_focus:
            self.query_one("#text-pane", VerticalScroll).focus()
        else:
            toc.focus()

    def action_previous_sentence(self) -> None:
        self.set_cursor(self.sentence_index - 1)
        self.after_sentence_change()

    def action_next_sentence(self) -> None:
        self.set_cursor(self.sentence_index + 1)
        self.after_sentence_change()

    def action_chapter_start(self) -> None:
        self.set_cursor(0)
        self.after_sentence_change()

    def action_chapter_end(self) -> None:
        self.set_cursor(len(self.sentences) - 1)
        self.after_sentence_change()

    def action_previous_chapter(self) -> None:
        self.goto_chapter(-1)

    def action_next_chapter(self) -> None:
        self.goto_chapter(1)

    def goto_chapter(self, offset: int) -> None:
        if not self.chapter_ids or not self.chapter:
            return
        current = self.chapter["chapter_id"]
        if current not in self.chapter_ids:
            return
        index = self.chapter_ids.index(current) + offset
        if index < 0 or index >= len(self.chapter_ids):
            return
        self.load_chapter(self.chapter_ids[index])
        self.after_sentence_change()

    def action_focus_toc(self) -> None:
        self.query_one("#toc-pane", VimListView).focus()

    def toggle_fullscreen(self) -> None:
        """Show the text in the whole screen, or shrink it back to one page."""
        self.set_class(not self.has_class("fullscreen"), "fullscreen")

    # -- 搜索 ------------------------------------------------------------
    def action_search(self) -> None:
        """Open the search prompt, the way vim does."""
        field = self.query_one("#search-input", Input)
        field.display = True
        field.focus()

    def action_next_hit(self) -> None:
        """Jump to the next search hit."""
        if not self._hits:
            return
        self._hit_index = (self._hit_index + 1) % len(self._hits)
        self.goto_hit(self._hits[self._hit_index])

    def action_previous_hit(self) -> None:
        """Jump to the previous search hit."""
        if not self._hits:
            return
        self._hit_index = (self._hit_index - 1) % len(self._hits)
        self.goto_hit(self._hits[self._hit_index])

    def goto_hit(self, hit: dict) -> None:
        """Move to a search hit."""
        chapter_id = hit.get("chapter_id")
        sentence_id = hit.get("sentence_id")
        if not chapter_id or not sentence_id:
            return
        if chapter_id != (self.chapter or {}).get("chapter_id"):
            self.load_chapter(chapter_id, sentence_id)
            return
        for position, sentence in enumerate(self.sentences):
            if sentence["id"] == sentence_id:
                self.set_cursor(position)
                break
        self.after_sentence_change()

    def run_search(self, query: str) -> None:
        """Search the book and show the hits in the directory pane."""
        if not query or not self.book_id:
            return
        try:
            payload = self.app.api.search(self.book_id, query, 50)
        except Exception as exc:  # noqa: BLE001
            self.notify(f"搜索失败：{exc}", title="错误", severity="error")
            return
        self._hits = payload.get("results", [])
        self._hit_index = -1
        self._pane_mode = "search"
        listing = self.query_one("#toc-pane", VimListView)
        listing.clear()
        if not self._hits:
            listing.append(ListItem(Static("（没有找到）")))
        for hit in self._hits:
            snippet = hit.get("snippet", "").replace("<em>", "").replace("</em>", "")
            listing.append(
                ListItem(
                    Static(
                        f"{hit.get('chapter_title', '')}\n{snippet[:60]}"
                    )
                )
            )
        listing.index = 0
        self.notify(f"找到 {payload.get('total', 0)} 处，按 n 逐个跳转", title="搜索")

    def restore_toc(self) -> None:
        """Put the directory back after a search."""
        self._pane_mode = "toc"
        self._hits = []
        self.render_toc()

    def action_back(self) -> None:
        self.app.pop_screen()

    def remember_position(self) -> None:
        """把位置记到本地文件里 —— 终端自己的位置，不发给任何人。"""
        if not self.cursor or not self.chapter:
            return
        self.progress.set(
            self.book_id,
            self.cursor["chapter_id"],
            self.cursor["sentence_id"],
            self.cursor.get("word_index"),
        )

    def schedule_percent(self) -> None:
        """停下来一会儿再去问百分比，别每挪一句就发一次请求。"""
        if self._percent_timer is not None:
            self._percent_timer.stop()
        self._percent_timer = self.set_timer(0.8, self.refresh_percent)

    def refresh_percent(self) -> None:
        if not self.cursor:
            return
        try:
            percent = self.app.api.percent(
                self.book_id, self.cursor["chapter_id"], self.cursor["sentence_id"]
            )
        except Exception:  # noqa: BLE001 - 百分比算不出来不影响阅读
            return
        self.progress.set(
            self.book_id,
            self.cursor["chapter_id"],
            self.cursor["sentence_id"],
            self.cursor.get("word_index"),
            percent,
        )
        self.update_status()

    # -- events ----------------------------------------------------------
    def on_input_submitted(self, event: Input.Submitted) -> None:
        """The search prompt was confirmed."""
        field = self.query_one("#search-input", Input)
        query = event.value.strip()
        field.display = False
        field.value = ""
        if query:
            self.run_search(query)

    def on_input_changed(self, event: Input.Changed) -> None:
        """The user emptied the search box: the directory comes back.

        The check on ``display`` keeps the program from undoing its own
        results — after a search the box is hidden and cleared, and that must
        not wipe the hits that were just found.
        """
        if (
            event.input.id == "search-input"
            and event.value.strip() == ""
            and event.input.display
        ):
            self.restore_toc()

    def on_key(self, event: Key) -> None:
        """Escape leaves the search prompt."""
        if event.key == "escape" and self.query_one("#search-input", Input).display:
            field = self.query_one("#search-input", Input)
            field.display = False
            field.value = ""
            self.restore_toc()
            event.stop()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Jump to the directory entry that was selected."""
        index = event.list_view.index
        if index is None:
            return
        if self._pane_mode == "search":
            if 0 <= index < len(self._hits):
                self._hit_index = index
                self.goto_hit(self._hits[index])
            return
        if index >= len(self.toc_flat):
            return
        node, _ = self.toc_flat[index]
        chapter_id = node.get("chapter_id")
        if not chapter_id:
            return
        anchor = node.get("anchor")
        if chapter_id != (self.chapter or {}).get("chapter_id"):
            self.load_chapter(chapter_id)
        if anchor:
            self.jump_to_anchor(anchor)
        else:
            self.set_cursor(0)
        self.after_sentence_change()

    def jump_to_anchor(self, anchor: str) -> None:
        """Move to the block that carries an anchor."""
        for position, sentence in enumerate(self.sentences):
            if f".{anchor}" in sentence["id"] or sentence["id"].endswith(anchor):
                self.set_cursor(position)
                return
        self.set_cursor(0)

    def after_sentence_change(self) -> None:
        """Hook for the listening screen."""
        return


class ReaderScreen(BaseReaderScreen):
    """The reading screen."""

    BINDINGS = [
        Binding("space", "listen", "播放"),
        Binding("p", "listen", "播放"),
    ]

    def action_listen(self) -> None:
        """Switch to the listening screen."""
        from lector_tui.screens.listen import ListenScreen

        chapter_id = (self.chapter or {}).get("chapter_id")
        self.app.push_screen(ListenScreen(self.book_id, chapter_id, self.sentence_index))


class ListenScreen(BaseReaderScreen):
    """The listening screen: reading plus an audio panel."""

    BINDINGS = [
        Binding("space", "toggle", "播放/暂停"),
        Binding("p", "toggle", "播放/暂停"),
        Binding("r", "replay", "重播"),
        Binding("plus", "faster", "加速"),
        Binding("equals", "faster", "加速"),
        Binding("minus", "slower", "减速"),
        Binding("0", "reset_rate", "原速"),
    ]

    def __init__(self, book_id: str, chapter_id: str | None = None, sentence_index: int = 0) -> None:
        super().__init__(book_id)
        self.start_chapter = chapter_id
        self.start_index = sentence_index
        self.playing = False
        self._timer = None
        self._clock = None
        self._last_word_index: int | None = None

    def compose(self) -> ComposeResult:
        with Vertical():
            with Horizontal(id="reader-body"):
                yield VimListView(id="toc-pane")
                with Vertical(id="text-area"):
                    yield ImageScroll(ChapterText(), id="text-pane")
            yield Input(placeholder="搜索全书…（回车确认，Esc 取消）", id="search-input")
            yield Static("", id="audio-panel")
            yield Static("", id="status-bar")
            yield Footer()

    def on_mount(self) -> None:
        self.query_one("#search-input").display = False
        # 焦点默认在正文：h/j/k/l 是读的时候最常用的键。
        # 按 Tab 切到目录，目录里 j/k/l 才是目录自己的键。
        self.query_one("#text-pane", VerticalScroll).focus()
        self.load_book()
        if self.start_chapter and self.chapter and self.chapter.get("chapter_id") != self.start_chapter:
            self.load_chapter(self.start_chapter)
        if self.chapter and self.sentences:
            self.set_cursor(self.start_index)
        self.update_audio_panel()
        # Entering the listening screen starts the narration.
        self.start_playback()

    def action_toggle(self) -> None:
        """Start or stop the narration."""
        if self.playing:
            self.stop_playback()
        else:
            self.start_playback()

    def action_replay(self) -> None:
        """Restart the current sentence."""
        if not self.playing:
            self.start_playback()
            return
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        self._play_current()

    def action_faster(self) -> None:
        self._set_rate(self.app.audio.rate + 0.25)

    def action_slower(self) -> None:
        self._set_rate(self.app.audio.rate - 0.25)

    def action_reset_rate(self) -> None:
        self._set_rate(1.0)

    def _set_rate(self, rate: float) -> None:
        self.app.audio.rate = max(0.75, min(2.0, round(rate, 2)))
        self.notify(f"倍速：{self.app.audio.rate:.2f}×", title="听书")
        if self.playing:
            self._play_current()
        else:
            self.update_audio_panel()

    def start_playback(self) -> None:
        """Play the current sentence and continue with the next ones."""
        sentence = self.current_sentence
        if sentence is None:
            return
        self.playing = True
        self.update_audio_panel()
        self._play_current()

    def _play_current(self) -> None:
        from lector_tui.audio import Clock

        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        self.app.audio.stop()
        sentence = self.current_sentence
        if sentence is None:
            self.stop_playback()
            return
        try:
            target = self.app.audio.tempdir() / f"{sentence['id'].replace('.', '_')}.mp3"
            self.app.api.download_audio(self.book_id, sentence["id"], str(target))
        except Exception as exc:  # noqa: BLE001
            self.notify(f"音频不可用：{exc}", title="错误", severity="error")
            self.stop_playback()
            return
        try:
            payload = self.app.api.get_words(self.book_id, sentence["id"])
        except Exception:  # noqa: BLE001
            payload = {"words": [], "granularity": "sentence"}
        self.words = payload.get("words", [])
        self.granularity = payload.get("granularity", "sentence")
        self._last_word_index = 0 if self.words else -1
        self.query_one(ChapterText).set_words(self.words, self._last_word_index)
        try:
            self.app.audio.play(str(target))
        except Exception as exc:  # noqa: BLE001
            self.notify(f"无法播放：{exc}", title="错误", severity="error")
            self.stop_playback()
            return
        self._clock = Clock()
        self._timer = self.set_interval(0.1, self._tick)
        self.update_audio_panel()
        self._prefetch_next()

    def _prefetch_next(self) -> None:
        """趁当前句还在播，把下一句下载下来。

        不然每次换句都要等一次网络，节奏会一顿一顿的。
        """
        sentences = self.sentences
        index = next(
            (i for i, s in enumerate(sentences) if s["id"] == self.current_sentence["id"]),
            -1,
        ) if self.current_sentence else -1
        if index < 0:
            return
        following = sentences[index + 1] if index + 1 < len(sentences) else None
        if following is None:
            return
        target = self.app.audio.tempdir() / f"{following['id'].replace('.', '_')}.mp3"
        if target.exists():
            return
        try:
            self.app.api.download_audio(
                self.book_id, following["id"], str(target)
            )
        except Exception:  # noqa: BLE001 - 预取失败不打扰用户
            pass

    def _tick(self) -> None:
        """Advance the word highlight and the sentence."""
        if not self.playing or self._clock is None:
            return
        elapsed = self._clock.elapsed * self.app.audio.effective_rate
        words = getattr(self, "words", [])
        index = -1
        for position, word in enumerate(words):
            if elapsed >= word.get("start", 0) and elapsed < word.get("end", 0):
                index = position
                break
        if index != self._last_word_index:
            self._last_word_index = index
            self.query_one(ChapterText).set_words(words, index)
        if self.app.audio._process is not None and self.app.audio._process.poll() is not None:
            self._advance()

    def _advance(self) -> None:
        """The sentence finished — go to the next one."""
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        if self.sentence_index + 1 >= len(self.sentences):
            self.stop_playback()
            return
        self.set_cursor(self.sentence_index + 1)
        self._play_current()

    def stop_playback(self) -> None:
        """Stop the narration."""
        self.playing = False
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        self.app.audio.stop()
        try:
            self.query_one(ChapterText).set_words([], -1)
            self.update_audio_panel()
        except Exception:  # noqa: BLE001 - the screen may already be gone
            pass

    def update_audio_panel(self) -> None:
        """The three line audio panel."""
        try:
            panel = self.query_one("#audio-panel", Static)
        except Exception:  # noqa: BLE001 - the panel may not exist yet
            return
        sentence = self.current_sentence
        chapter_title = self.chapter.get("title", "") if self.chapter else ""
        words = getattr(self, "words", [])
        position = getattr(self, "_clock", None)
        elapsed = position.elapsed * self.app.audio.effective_rate if position else 0.0
        preview = sentence["text"][:56] if sentence else ""
        marker = "▶" if self.playing else "⏸"
        bar_width = 30
        progress = 0.0
        if words:
            last = words[-1].get("end", 0) or 1
            progress = min(1.0, elapsed / last)
        filled = int(bar_width * progress)
        bar = "▓" * filled + "░" * (bar_width - filled)
        text = (
            f" {marker} ⏮ ⏭  {chapter_title} · {elapsed:.1f}s · "
            f"{self.app.audio.rate:.1f}× · {self.app.audio.backend or '无播放器'}\n"
            f" {bar}\n"
            f" 当前句：{preview}"
        )
        panel.update(text)

    def after_sentence_change(self) -> None:
        if self.playing:
            self._play_current()

    def on_unmount(self) -> None:
        self.stop_playback()
