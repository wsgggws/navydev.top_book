"""Screen two — reading, and screen three — listening.

Both screens show the same blocks and sentences; the listening screen adds the
audio panel and the word highlight.  They share the position, so switching
between them never loses the place.
"""

from __future__ import annotations

from rich.style import Style
from rich.text import Text

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, ListItem, ListView, Static

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


class ChapterText(Static):
    """The text of the current chapter."""

    COMPONENT_CLASSES = {
        "chapter-title",
        "sentence-current",
        "word-read",
        "word-now",
    }

    def __init__(self) -> None:
        super().__init__()
        self.chapter: dict | None = None
        self.current_sentence: str | None = None
        self.words: list[dict] = []
        self.word_index: int = -1

    def set_chapter(self, chapter: dict) -> None:
        self.chapter = chapter
        self.refresh_content()

    def set_cursor(self, sentence_id: str) -> None:
        self.current_sentence = sentence_id
        self.words = []
        self.word_index = -1
        self.refresh_content()

    def set_words(self, words: list[dict], word_index: int) -> None:
        self.words = words
        self.word_index = word_index
        self.refresh_content()

    def refresh_content(self) -> None:
        self.update(self.build())

    # -- styles ----------------------------------------------------------
    def _style(self, name: str) -> Style:
        """The Rich style behind a component class."""
        try:
            return self.get_component_styles(name).rich_style
        except Exception:  # noqa: BLE001 - a missing class must not break the text
            return Style()

    def build(self) -> Text:
        """The chapter as rich text, with the cursor line on the current sentence."""
        text = Text()
        if not self.chapter:
            return text
        title_style = self._style("chapter-title")
        current_style = self._style("sentence-current")
        read_style = self._style("word-read")
        now_style = self._style("word-now")
        text.append(f"{self.chapter.get('title', '')}\n", style=title_style)
        text.append("\n")
        for block in self.chapter.get("blocks", []):
            if block.get("type") == "img":
                if block.get("alt"):
                    text.append(f"[图：{block['alt']}]\n", style=Style(dim=True))
                continue
            if block.get("type") == "hr":
                text.append("─" * 40 + "\n")
                continue
            heading = Style(bold=True) if block.get("type", "p").startswith("h") else Style()
            for sentence in block.get("sentences", []):
                if sentence["id"] == self.current_sentence:
                    self._append_sentence(text, sentence, current_style, read_style, now_style)
                else:
                    text.append(sentence["text"], style=heading)
            text.append("\n")
        return text

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
        Binding("left", "previous_sentence", "上一句"),
        Binding("right", "next_sentence", "下一句"),
        Binding("bracketleft", "previous_chapter", "上一章"),
        Binding("bracketright", "next_chapter", "下一章"),
        Binding("g", "chapter_start", "章首"),
        Binding("G", "chapter_end", "章末"),
        Binding("tab", "focus_toc", "目录"),
        Binding("s", "push_progress", "同步进度"),
        Binding("S", "pull_progress", "拉取进度"),
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

    # -- layout ----------------------------------------------------------
    def compose(self) -> ComposeResult:
        with Vertical():
            with Horizontal(id="reader-body"):
                yield ListView(id="toc-pane")
                yield VerticalScroll(ChapterText(), id="text-pane")
            yield Static("", id="status-bar")
            yield Footer()

    def on_mount(self) -> None:
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
        progress = detail.get("progress") or {}
        cursor = progress.get("cursor")
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
        listing = self.query_one("#toc-pane", ListView)
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
        self.update_status()

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

    def scroll_to_cursor(self) -> None:
        """Keep the current sentence visible."""
        pane = self.query_one("#text-pane", VerticalScroll)
        # Count the lines before the current sentence to scroll roughly there.
        offset = 0
        for sentence in self.sentences[: self.sentence_index]:
            offset += max(1, len(sentence["text"]) // 60 + 1)
        pane.scroll_to(y=max(0, offset - 3), animate=False)

    def update_status(self) -> None:
        """The status line at the bottom."""
        total = len(self.sentences)
        current = self.sentence_index + 1
        percent = int((current / total * 100) if total else 0)
        chapter_title = self.chapter.get("title", "") if self.chapter else ""
        self.query_one("#status-bar", Static).update(
            f" {chapter_title} · {percent}% · 句 {current}/{total} · "
            "s 同步 · Space 听书 · q 返回"
        )

    # -- actions ---------------------------------------------------------
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
        self.query_one("#toc-pane", ListView).focus()

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_push_progress(self) -> None:
        """Send the position to the server."""
        if not self.cursor:
            return
        try:
            self.app.api.set_progress(
                self.book_id,
                self.cursor["chapter_id"],
                self.cursor["sentence_id"],
                self.cursor.get("word_index"),
            )
            self.notify("进度已同步", title="进度")
        except Exception as exc:  # noqa: BLE001
            self.notify(f"同步失败：{exc}", title="错误", severity="error")

    def action_pull_progress(self) -> None:
        """Take the position from the server."""
        try:
            progress = self.app.api.get_progress(self.book_id)
        except Exception as exc:  # noqa: BLE001
            self.notify(f"拉取失败：{exc}", title="错误", severity="error")
            return
        cursor = progress.get("cursor")
        if not cursor:
            self.notify("服务器上没有进度", title="进度")
            return
        if cursor["chapter_id"] != (self.chapter or {}).get("chapter_id"):
            self.load_chapter(cursor["chapter_id"], cursor["sentence_id"])
        else:
            for position, sentence in enumerate(self.sentences):
                if sentence["id"] == cursor["sentence_id"]:
                    self.set_cursor(position)
                    break
        self.notify("已拉取服务器进度", title="进度")

    # -- events ----------------------------------------------------------
    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Jump to the directory entry that was selected."""
        index = event.list_view.index
        if index is None or index >= len(self.toc_flat):
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
        Binding("space", "listen", "听书"),
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
    ]

    def __init__(self, book_id: str, chapter_id: str | None = None, sentence_index: int = 0) -> None:
        super().__init__(book_id)
        self.start_chapter = chapter_id
        self.start_index = sentence_index
        self.playing = False
        self._timer = None
        self._clock = None

    def compose(self) -> ComposeResult:
        with Vertical():
            with Horizontal(id="reader-body"):
                yield ListView(id="toc-pane")
                yield VerticalScroll(ChapterText(), id="text-pane")
            yield Static("", id="audio-panel")
            yield Static("", id="status-bar")
            yield Footer()

    def on_mount(self) -> None:
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
        try:
            self.app.audio.play(str(target))
        except Exception as exc:  # noqa: BLE001
            self.notify(f"无法播放：{exc}", title="错误", severity="error")
            self.stop_playback()
            return
        self._clock = Clock()
        self._timer = self.set_interval(0.1, self._tick)
        self.update_audio_panel()

    def _tick(self) -> None:
        """Advance the word highlight and the sentence."""
        if not self.playing or self._clock is None:
            return
        elapsed = self._clock.elapsed
        words = getattr(self, "words", [])
        index = -1
        for position, word in enumerate(words):
            if elapsed >= word.get("start", 0) and elapsed < word.get("end", 0):
                index = position
                break
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
        elapsed = position.elapsed if position else 0.0
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
