"""Screen one — the bookshelf."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Footer, Input, Label, ListItem, ListView, Static

from lector_tui.screens.reader import ReaderScreen


class LibraryScreen(Screen):
    """The shelf: every book the server knows about."""

    BINDINGS = [
        Binding("enter", "open", "打开"),
        Binding("u", "upload", "上传"),
        Binding("d", "delete", "删除"),
        Binding("r", "refresh", "刷新"),
        Binding("q", "quit", "退出"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._books: list[dict] = []

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("  Lector  书架", id="shelf-title")
            yield ListView(id="library-list")
            yield Input(placeholder="上传本地 EPUB 的路径…", id="upload-input")
            yield Footer()

    def on_mount(self) -> None:
        self.query_one("#upload-input").display = False
        self.refresh_books()

    # -- data ------------------------------------------------------------
    def refresh_books(self) -> None:
        """Reload the shelf from the server."""
        listing = self.query_one("#library-list")
        listing.clear()
        try:
            self._books = self.app.api.list_books()
        except Exception as exc:  # noqa: BLE001 - the shelf must not crash
            self.notify(f"无法读取书架：{exc}", title="错误", severity="error")
            return
        if not self._books:
            listing.append(ListItem(Label("（空）按 u 上传一本 EPUB")))
            return
        for book in self._books:
            percent = int((book.get("progress") or 0) * 100)
            label = Label(
                f"▸ {book['title']}\n"
                f"  {book.get('author') or '未知作者'}   "
                f"{percent}%  {book.get('language') or ''}"
            )
            listing.append(ListItem(label))
        listing.index = 0

    # -- actions ---------------------------------------------------------
    def action_open(self) -> None:
        """Open the selected book."""
        listing = self.query_one("#library-list")
        index = listing.index
        if index is None or index >= len(self._books):
            return
        book = self._books[index]
        self.app.push_screen(ReaderScreen(book["book_id"]))

    def action_upload(self) -> None:
        """Ask for the path of a local EPUB."""
        upload = self.query_one("#upload-input")
        upload.display = True
        upload.focus()

    def action_delete(self) -> None:
        """Delete the selected book."""
        listing = self.query_one("#library-list")
        index = listing.index
        if index is None or index >= len(self._books):
            return
        book = self._books[index]
        try:
            self.app.api.delete_book(book["book_id"])
        except Exception as exc:  # noqa: BLE001
            self.notify(f"删除失败：{exc}", title="错误", severity="error")
            return
        self.notify(f"已删除《{book['title']}》")
        self.refresh_books()

    def action_refresh(self) -> None:
        self.refresh_books()

    # -- events ----------------------------------------------------------
    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Enter opens the book."""
        self.action_open()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        path = event.value.strip().strip('"')
        upload = self.query_one("#upload-input")
        upload.display = False
        upload.value = ""
        if not path:
            return
        if not Path_exists(path):
            self.notify(f"找不到文件：{path}", title="错误", severity="error")
            return
        try:
            payload = self.app.api.upload_book(path)
        except Exception as exc:  # noqa: BLE001
            self.notify(f"上传失败：{exc}", title="错误", severity="error")
            return
        self.notify(
            f"已上传《{payload['book']['title']}》"
            if not payload.get("duplicate")
            else "这本书已经在书架上了"
        )
        self.refresh_books()


def Path_exists(path: str) -> bool:
    """Whether a local path exists."""
    import os

    return os.path.isfile(path)
