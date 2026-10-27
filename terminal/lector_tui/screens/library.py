"""Screen one — the bookshelf.

The terminal client is a reader: it looks at the shelf, it does not change it.
Books are published from the repository; the client only reads them.
"""

from __future__ import annotations

from io import BytesIO

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Input, ListItem, Static
from lector_tui.image_widget import TerminalImage, image_error

from lector_tui.cache import ImageCache
from lector_tui.config import ProgressStore
from lector_tui.images import placeholder_cover
from lector_tui.image_data import decode_image
from lector_tui.widgets import VimListView
from lector_tui.shelf_cache import ShelfCache, valid_books

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
            yield TerminalImage(
                image=BytesIO(placeholder_cover()),
                classes="book-cover",
                on_error=image_error,
            )
            with Vertical(classes="book-info"):
                yield Static(book["title"], classes="book-title", markup=False)
                yield Static(
                    f"{book.get('author') or '未知作者'}\n{book.get('language') or ''}  ·  已读 {self.percent}%",
                    classes="book-meta",
                    markup=False,
                )

    def set_cover(self, data: bytes) -> None:
        """Swap the loading box for the downloaded cover."""
        decoded = decode_image(data)
        if decoded is None:
            return
        try:
            self.query_one(TerminalImage).image = decoded
        except Exception:  # noqa: BLE001 - a cover must never break the shelf
            return

    def set_percent(self, percent: int) -> None:
        self.percent = percent
        self.query_one(".book-meta", Static).update(
            f"{self.book.get('author') or '未知作者'}\n{self.book.get('language') or ''}  ·  已读 {percent}%"
        )


class LibraryScreen(Screen):
    """The shelf: every book the server knows about."""

    # 终端端只读，书籍由仓库发布。
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
        self._refresh_generation = 0
        self._snapshot_key = None
        self._has_snapshot = False

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("  navy's ebook (有声朗读，逐词高亮，本机续读)  书架", id="shelf-title", markup=False)
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

    def show_server(self, status: str = "") -> None:
        """Show which server the shelf is talking to."""
        suffix = f"  · {status}" if status else ""
        self.query_one("#shelf-server", Static).update(f"  {self.app.config.describe()}{suffix}")

    # -- data ------------------------------------------------------------
    def refresh_books(self) -> None:
        """Paint a local snapshot immediately; update it off the UI thread."""
        api = self.app.api
        key = (api.base_url.rstrip("/"), api.token)
        self._refresh_generation += 1
        generation = self._refresh_generation
        snapshot = ShelfCache(*key)
        if self._snapshot_key != key:
            self.workers.cancel_group(self, "book-covers")
            self._snapshot_key = key
            self._has_snapshot = False
            self._books = []
            cached = snapshot.get()
            if cached is not None:
                self._render_books(cached)
            else:
                listing = self.query_one("#library-list", VimListView)
                listing.clear()
                listing.append(ListItem(Static("正在加载书架…")))
        self.show_server("本地书架 · 正在刷新…" if self._has_snapshot else "正在加载书架…")

        def worker():
            from textual.worker import get_current_worker

            try:
                books = api.list_books()
                if not valid_books(books):
                    raise ValueError("书架数据格式不正确")
                if get_current_worker().is_cancelled:
                    return
                snapshot.put(books)
                callback, result = self._books_loaded, books
            except Exception as exc:  # noqa: BLE001 - preserve a usable offline shelf
                callback, result = self._books_failed, str(exc)
            if not get_current_worker().is_cancelled:
                try:
                    self.app.call_from_thread(callback, generation, key, result)
                except Exception:  # noqa: BLE001 - application may have exited
                    return

        self.run_worker(worker, group="book-list", exclusive=True, thread=True)

    def _books_loaded(self, generation, key, books) -> None:
        if generation != self._refresh_generation or key != self._snapshot_key:
            return
        self._render_books(books)
        self.show_server()

    def _books_failed(self, generation, key, error) -> None:
        if generation != self._refresh_generation or key != self._snapshot_key:
            return
        self.show_server("本地书架 · 刷新失败" if self._has_snapshot else "连接失败 · r 重试 / c 连接设置")
        if not self._has_snapshot:
            listing = self.query_one("#library-list", VimListView)
            listing.clear()
            listing.append(ListItem(Static("暂时无法读取书架，按 r 重试或 c 配置连接。")))
        self.notify(f"无法刷新书架：{error}", title="连接", severity="warning")

    def _render_books(self, books: list[dict]) -> None:
        listing = self.query_one("#library-list", VimListView)
        progress = ProgressStore.load()
        if self._has_snapshot and books == self._books:
            for item in listing.query(BookItem):
                item.set_percent(int(progress.percent(item.book["book_id"]) * 100))
            return
        selected = self._books[listing.index]["book_id"] if listing.index is not None and listing.index < len(self._books) else None
        self.workers.cancel_group(self, "book-covers")
        listing.clear()
        self._books = books
        self._has_snapshot = True
        if not self._books:
            listing.append(ListItem(Static("（空）")))
            return
        # 进度是这台机器的终端自己记的，跟网页和服务器都无关。
        items: list[BookItem] = []
        for book in self._books:
            percent = int(progress.percent(book["book_id"]) * 100)
            item = BookItem(book, percent)
            listing.append(item)
            items.append(item)
        listing.index = next((i for i, book in enumerate(books) if book["book_id"] == selected), 0)
        self.call_after_refresh(self._load_covers, items)

    def _load_covers(self, items: list[BookItem]) -> None:
        """Download covers off the UI thread and fill them in as they arrive."""

        api = self.app.api
        cache = ImageCache(namespace=api.base_url.rstrip("/"))

        def worker() -> None:
            from textual.worker import get_current_worker

            for item in items:
                if get_current_worker().is_cancelled:
                    return
                book = item.book
                book_id = book["book_id"]
                if not book.get("cover_url"):
                    continue
                cache_name = f"cover:{book['cover_url']}"
                data = cache.get(book_id, cache_name)
                if data is None:
                    try:
                        data = api.fetch_cover(book_id)
                    except Exception:  # noqa: BLE001 - fall back to a blank cover
                        continue
                    cache.put(book_id, cache_name, data)
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
