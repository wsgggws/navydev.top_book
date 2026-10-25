"""Screen one — the bookshelf.

The terminal client is a reader: it looks at the shelf, it does not change it.
Uploading and deleting books are the web client's business.
"""

from __future__ import annotations

from io import BytesIO

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Input, ListItem, Static
from textual_image.widget import Image as TerminalImage

from lector_tui.config import ProgressStore
from lector_tui.widgets import VimListView

from lector_tui.screens.reader import ReaderScreen


class BookItem(ListItem):
    """One shelf row: cover on the left, title and metadata on the right."""

    def __init__(self, book: dict, percent: int) -> None:
        super().__init__()
        self.book = book
        self.percent = percent

    def compose(self) -> ComposeResult:
        book = self.book
        with Horizontal(classes="book-row"):
            yield TerminalImage(classes="book-cover")
            with Vertical(classes="book-info"):
                yield Static(book["title"], classes="book-title")
                yield Static(
                    f"{book.get('author') or '未知作者'}\n"
                    f"{book.get('language') or ''}  ·  已读 {self.percent}%",
                    classes="book-meta",
                )

    def set_cover(self, data: bytes) -> None:
        """Swap the loading box for the downloaded cover."""
        try:
            self.query_one(TerminalImage).image = BytesIO(data)
        except Exception:  # noqa: BLE001 - a cover must never break the shelf
            return


class LibraryScreen(Screen):
    """The shelf: every book the server knows about."""

    # 终端端只读：上传与删除是网页端的事，终端不碰书架。
    BINDINGS = [
        Binding("enter", "open", "打开"),
        Binding("space", "listen", "听书"),
        Binding("r", "refresh", "刷新"),
        Binding("c", "connect", "连接"),
        Binding("g", "first_book", "首本"),
        Binding("G", "last_book", "末本"),
        Binding("q", "quit", "退出"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._books: list[dict] = []
        self._cover_cache: dict[str, bytes] = {}

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("  有声电子书  书架", id="shelf-title")
            yield Static("", id="shelf-server")
            yield VimListView(id="library-list")
            yield Input(placeholder="服务器地址，例如 https://navydev.top/ebook", id="connect-url")
            yield Input(placeholder="访问令牌（没有就留空）", id="connect-token")
            yield Footer()

    def on_mount(self) -> None:
        self.query_one("#connect-url").display = False
        self.query_one("#connect-token").display = False
        self.show_server()
        self.refresh_books()

    def show_server(self) -> None:
        """Show which server the shelf is talking to."""
        self.query_one("#shelf-server", Static).update(f"  {self.app.config.describe()}")

    # -- data ------------------------------------------------------------
    def refresh_books(self) -> None:
        """Reload the shelf from the server."""
        listing = self.query_one("#library-list", VimListView)
        listing.clear()
        try:
            self._books = self.app.api.list_books()
        except Exception as exc:  # noqa: BLE001 - the shelf must not crash
            self.notify(f"无法读取书架：{exc}", title="错误", severity="error")
            return
        if not self._books:
            listing.append(ListItem(Static("（空）")))
            return
        # 进度是这台机器的终端自己记的，跟网页和服务器都无关。
        progress = ProgressStore.load()
        items: list[BookItem] = []
        for book in self._books:
            percent = int(progress.percent(book["book_id"]) * 100)
            item = BookItem(book, percent)
            listing.append(item)
            items.append(item)
        listing.index = 0
        self.call_after_refresh(self._load_covers, items)

    def _load_covers(self, items: list[BookItem]) -> None:
        """Download covers off the UI thread and fill them in as they arrive."""

        def worker() -> None:
            for item in items:
                book = item.book
                book_id = book["book_id"]
                if not book.get("cover_url"):
                    continue
                data = self._cover_cache.get(book_id)
                if data is None:
                    try:
                        data = self.app.api.fetch_cover(book_id)
                    except Exception:  # noqa: BLE001 - fall back to a blank cover
                        continue
                    self._cover_cache[book_id] = data
                try:
                    self.app.call_from_thread(item.set_cover, data)
                except Exception:  # noqa: BLE001 - the shelf may have been closed
                    return

        self.run_worker(worker, group="book-covers", exclusive=True, thread=True)

    # -- actions ---------------------------------------------------------
    def action_open(self) -> None:
        """Open the selected book."""
        listing = self.query_one("#library-list", VimListView)
        index = listing.index
        if index is None or index >= len(self._books):
            return
        book = self._books[index]
        self.app.push_screen(ReaderScreen(book["book_id"]))

    def action_listen(self) -> None:
        """Open the selected book and start listening immediately."""
        listing = self.query_one("#library-list", VimListView)
        index = listing.index
        if index is None or index >= len(self._books):
            return
        from lector_tui.screens.listen import ListenScreen

        self.app.push_screen(ListenScreen(self._books[index]["book_id"]))

    def action_first_book(self) -> None:
        listing = self.query_one("#library-list", VimListView)
        if self._books:
            listing.index = 0

    def action_last_book(self) -> None:
        listing = self.query_one("#library-list", VimListView)
        if self._books:
            listing.index = len(self._books) - 1

    def action_refresh(self) -> None:
        """Reload the shelf."""
        self.refresh_books()

    def action_connect(self) -> None:
        """Ask for the address of the server and the access token."""
        url_input = self.query_one("#connect-url", Input)
        token_input = self.query_one("#connect-token", Input)
        url_input.display = True
        token_input.display = True
        url_input.value = self.app.config.url
        token_input.value = self.app.config.token
        url_input.focus()

    def action_quit(self) -> None:
        """Leave the application from the shelf."""
        self.app.exit()

    # -- events ----------------------------------------------------------
    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Enter opens the book."""
        self.action_open()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """The connect prompt was confirmed."""
        if event.input.id == "connect-url":
            self.query_one("#connect-token", Input).focus()
            return
        if event.input.id == "connect-token":
            url = self.query_one("#connect-url", Input).value.strip().rstrip("/")
            token = self.query_one("#connect-token", Input).value.strip()
            for field in ("#connect-url", "#connect-token"):
                self.query_one(field, Input).display = False
            if not url:
                return
            self.app.connect_to(url, token)
            self.show_server()
            self.notify(f"已连接到 {url}", title="连接")
            self.refresh_books()
            return
