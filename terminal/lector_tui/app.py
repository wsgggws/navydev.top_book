"""The Textual application.

Three screens — bookshelf, reading and listening — share one local position.
The browser keeps its own position independently.
"""

from __future__ import annotations

import argparse
from importlib.metadata import PackageNotFoundError, version

from textual.theme import Theme

from lector_tui.api import ApiClient
from lector_tui.audio import AudioPlayer
from lector_tui.config import ClientConfig
from lector_tui.image_app import ImageApp
from lector_tui.theme import _is_light, query_terminal_colors, resolve_theme

#: The three themes of the interface specification.
THEMES = {
    "paper": Theme(
        name="paper",
        primary="#23201c",
        secondary="#6b655c",
        accent="#c8791f",
        foreground="#23201c",
        background="#faf9f6",
        surface="#ffffff",
        panel="#f2f0ea",
        warning="#c8791f",
        error="#b3402f",
        success="#4a7c3f",
        dark=False,
    ),
    "sepia": Theme(
        name="sepia",
        primary="#3a3226",
        secondary="#7a6f5c",
        accent="#b06a12",
        foreground="#3a3226",
        background="#f4ecd8",
        surface="#faf3e0",
        panel="#ede3c9",
        warning="#b06a12",
        error="#b3402f",
        success="#4a7c3f",
        dark=False,
    ),
    "night": Theme(
        name="night",
        primary="#d8d5cf",
        secondary="#8b8781",
        accent="#e0a054",
        foreground="#d8d5cf",
        background="#16181c",
        surface="#1e2126",
        panel="#24272d",
        warning="#e0a054",
        error="#e0705f",
        success="#7fae6d",
        dark=True,
    ),
}

THEME_CYCLE = (
    "auto",
    "ansi-dark",
    "ansi-light",
    "dracula",
    "catppuccin-mocha",
    "catppuccin-frappe",
    "catppuccin-latte",
    "gruvbox",
    "nord",
    "solarized-dark",
    "solarized-light",
    "tokyo-night",
    "rose-pine",
    "paper",
    "sepia",
    "night",
)


class LectorApp(ImageApp):
    """The terminal application."""

    CSS = """
    Screen {
        background: $background;
        color: $foreground;
    }

    #library-list {
        height: 1fr;
        border: none;
    }

    #library-list > ListItem {
        padding: 0 1;
        border-left: solid $panel;
    }

    .book-row {
        height: auto;
        padding: 1 0;
    }

    .book-cover {
        width: 10;
        height: auto;
        margin-right: 2;
        background: $panel;
    }

    .book-info {
        width: 1fr;
        height: auto;
        align-vertical: middle;
    }

    .book-title {
        text-style: bold;
        color: $foreground;
    }

    .book-meta {
        color: $text-muted;
        margin-top: 1;
    }

    #library-list > ListItem.-highlight,
    #library-list:focus > ListItem.-highlight,
    #toc-pane > ListItem.-highlight,
    #toc-pane:focus > ListItem.-highlight {
        background: $panel;
        color: $foreground;
        border-left: solid $accent;
    }

    #reader-body {
        height: 1fr;
    }

    #toc-pane {
        width: 30;
        max-width: 40%;
        height: 1fr;
        border-right: solid $panel;
        overflow-y: auto;
    }

    #toc-pane > .toc-current Static {
        text-style: bold underline;
    }

    /* 扣除目录后居中；f 键填满右侧正文区。 */
    #text-area {
        width: 1fr;
        height: 1fr;
        align: center middle;
    }

    #text-pane {
        width: 92%;
        max-width: 96;
        height: 100%;
        max-height: 34;
        overflow-y: auto;
        /* 右侧固定两列滚动条槽 + 一列留白，与左侧三列对称。 */
        scrollbar-gutter: stable;
        scrollbar-size-vertical: 2;
        padding: 0 1 0 3;
        border-top: solid $panel;
        border-bottom: solid $panel;
    }

    Screen.fullscreen #text-pane {
        width: 100%;
        max-width: 100%;
        max-height: 100%;
        border-top: none;
        border-bottom: none;
    }

    #search-input {
        display: none;
        height: 3;
    }

    #search-input:focus {
        border: tall $accent;
    }

    #status-bar {
        height: 1;
        background: $panel;
        color: $text-muted;
    }

    #audio-panel {
        height: 3;
        background: $panel;
        border-top: solid $panel;
    }

    .chapter-title {
        text-style: bold;
        color: $accent;
    }

    .chapter-text {
        width: 1fr;
        height: auto;
    }

    .chapter-title-block {
        width: 1fr;
        height: auto;
        margin-bottom: 1;
    }

    .chapter-block {
        width: 1fr;
        height: auto;
        margin-bottom: 1;
    }

    .chapter-image-block {
        width: 1fr;
        height: auto;
        margin: 1 0 2 0;
    }

    .chapter-image {
        content-align: center middle;
        width: 100%;
        height: auto;
        margin-bottom: 1;
        background: $panel;
    }

    .chapter-image-loading,
    .chapter-image-caption {
        width: 1fr;
        height: auto;
        color: $text-muted;
    }

    .sentence-current {
        text-style: bold underline;
    }

    .word-read {
        text-style: dim;
    }

    .word-now {
        text-style: reverse bold;
    }

    .help-key {
        color: $accent;
        text-style: bold;
    }
    """

    BINDINGS = [
        ("ctrl+c", "quit", "退出"),
        ("m", "cycle_theme", "主题"),
        ("f", "toggle_fullscreen", "全屏"),
        ("question_mark", "help", "帮助"),
    ]

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        theme: str | None = None,
        theme_preference: str | None = None,
        terminal_colors: dict[str, str] | None = None,
    ) -> None:
        super().__init__()
        self.config = ClientConfig.load()
        if base_url:
            self.config.url = base_url.rstrip("/")
        if token is not None:
            self.config.token = token
        self.api = ApiClient(base_url=self.config.url, token=self.config.token)
        self.audio = AudioPlayer()
        for custom_theme in THEMES.values():
            self.register_theme(custom_theme)
        # Snapshot RGB colours instead of blending ANSI default (0,0,0).
        for name, fallback in (("ansi-light", THEMES["paper"]), ("ansi-dark", THEMES["night"])):
            colors = terminal_colors or {}
            background = colors.get("background", fallback.background)
            foreground = colors.get("foreground", fallback.foreground)
            accent = colors.get("accent", fallback.accent)
            bg = tuple(int(background[i : i + 2], 16) for i in (1, 3, 5))
            fg = tuple(int(foreground[i : i + 2], 16) for i in (1, 3, 5))
            panel = "#" + "".join(f"{round(b * 0.92 + f * 0.08):02x}" for b, f in zip(bg, fg))
            muted = "#" + "".join(f"{round(b * 0.35 + f * 0.65):02x}" for b, f in zip(bg, fg))
            self.register_theme(
                Theme(
                    name=name,
                    primary=accent,
                    secondary=accent,
                    accent=accent,
                    foreground=foreground,
                    background=background,
                    surface=background,
                    panel=panel,
                    dark=not _is_light(*bg),
                    variables={"text-muted": muted, "text-disabled": muted},
                )
            )
        preference = theme_preference or theme or self.config.theme
        self._apply_theme(preference, actual=theme, save=False)

    def on_mount(self) -> None:
        from lector_tui.screens.library import LibraryScreen

        self.push_screen(LibraryScreen())

    def connect_to(self, url: str, token: str) -> None:
        """Point the client at another server and remember it."""
        self.config.url = url.strip().rstrip("/")
        self.config.token = token.strip()
        self.config.save()
        self.api = ApiClient(base_url=self.config.url, token=self.config.token)

    def action_cycle_theme(self) -> None:
        """Cycle ANSI, popular terminal schemes, and the built-in themes."""
        try:
            index = THEME_CYCLE.index(self.theme_preference)
        except ValueError:
            index = 0
        preference = THEME_CYCLE[(index + 1) % len(THEME_CYCLE)]
        self._apply_theme(preference, notify=True)

    def _apply_theme(
        self,
        preference: str,
        *,
        actual: str | None = None,
        save: bool = True,
        notify: bool = False,
    ) -> None:
        preference = (preference or "auto").strip()
        resolved = actual or resolve_theme(preference)
        if resolved not in self.available_themes:
            resolved = "ansi-dark"
        self.theme_preference = preference
        self.theme = resolved
        if save:
            self.config.theme = preference
            self.config.save()
        if notify:
            self.notify(f"主题：{resolved}", title="外观")

    def action_toggle_fullscreen(self) -> None:
        """Show the text in the whole screen, or shrink it back."""
        screen = self.screen
        if hasattr(screen, "toggle_fullscreen"):
            screen.toggle_fullscreen()

    def action_help(self) -> None:
        """Show the key bindings."""
        self.notify(
            "hjkl 移动 · Space/p 播放暂停 · r 重播 · +/- 倍速 · v 男女声 · Ctrl+l 重绘 · / 搜索 · [ ] 换章 · t 目录 · f 全屏 · m 主题 · q 返回",
            title="快捷键",
            timeout=8,
        )

    def on_exit(self) -> None:
        self.audio.cleanup()


def _version() -> str:
    """The client version, also baked into the standalone binary."""
    try:
        from lector_tui._build_info import VERSION

        return VERSION
    except ImportError:
        pass
    try:
        return version("lector-tui")
    except PackageNotFoundError:
        return "dev"


def main(argv: list[str] | None = None) -> None:
    """Entry point of the terminal client."""
    parser = argparse.ArgumentParser(
        prog="lector",
        description="只读终端客户端：阅读和收听 navydev.top/ebook。",
    )
    parser.add_argument("--url", help="服务端地址，默认 https://navydev.top/ebook")
    parser.add_argument("--token", help="LECTOR_TOKEN；也可用环境变量")
    parser.add_argument(
        "--theme",
        help="auto（默认）、ansi-dark、ansi-light、dracula、catppuccin-mocha 等",
    )
    parser.add_argument("--check", action="store_true", help="检查服务器连接后退出")
    parser.add_argument("--version", action="version", version=f"%(prog)s {_version()}")
    args = parser.parse_args(argv)

    config = ClientConfig.load()
    if args.check:
        client = ApiClient(
            base_url=args.url or config.url,
            token=args.token if args.token is not None else config.token,
        )
        try:
            health = client.health()
            books = client.list_books()
        except Exception as exc:  # noqa: BLE001 - a CLI probe should explain failure
            print(f"连接失败：{exc}")
            raise SystemExit(1) from exc
        print(f"OK {client.base_url} · {health.get('status', 'unknown')} · {len(books)} books")
        return

    # Probe graphics before Textual starts reading stdin, after all one-shot
    # commands have exited. Otherwise Textual can consume the probe replies.
    from lector_tui.screens import library  # noqa: F401

    preference = args.theme or config.theme
    colors = query_terminal_colors()
    LectorApp(
        base_url=args.url,
        token=args.token,
        theme=resolve_theme(preference, colors=colors),
        theme_preference=preference,
        terminal_colors=colors,
    ).run()


if __name__ == "__main__":
    main()
