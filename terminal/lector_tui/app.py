"""The Textual application.

Three screens — bookshelf, reading and listening — share one position, the
same one the browser uses.
"""

from __future__ import annotations

import os

from textual.app import App
from textual.theme import Theme

from lector_tui.api import ApiClient
from lector_tui.audio import AudioPlayer
from lector_tui.config import ClientConfig
from lector_tui.screens.library import LibraryScreen

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


class LectorApp(App):
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

    #library-list:focus > ListItem.-selected {
        background: $panel;
        border-left: solid $accent;
    }

    #reader-body {
        height: 1fr;
    }

    #toc-pane {
        width: 30;
        height: 1fr;
        border-right: solid $panel;
        overflow-y: auto;
    }

    /* 正文不必铺满整屏：默认只占中间一页，f 键切到全屏。 */
    #text-area {
        width: 1fr;
        height: 1fr;
        align: center middle;
    }

    #text-pane {
        width: 1fr;
        height: auto;
        max-height: 26;
        overflow-y: auto;
        padding: 0 2;
        border-top: solid $panel;
        border-bottom: solid $panel;
    }

    Screen.fullscreen #text-pane {
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

    .sentence-current {
        background: $accent 35%;
        text-style: bold;
    }

    .word-read {
        background: $panel;
    }

    .word-now {
        background: $accent 55%;
        text-style: bold;
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

    def __init__(self, base_url: str | None = None, token: str | None = None) -> None:
        super().__init__()
        self.config = ClientConfig.load()
        if base_url:
            self.config.url = base_url.rstrip("/")
        if token is not None:
            self.config.token = token
        self.api = ApiClient(base_url=self.config.url, token=self.config.token)
        self.audio = AudioPlayer()
        for theme in THEMES.values():
            self.register_theme(theme)
        self.theme = os.environ.get("LECTOR_THEME", "paper")
        if self.theme not in THEMES:
            self.theme = "paper"

    def on_mount(self) -> None:
        self.push_screen(LibraryScreen())

    def connect_to(self, url: str, token: str) -> None:
        """Point the client at another server and remember it."""
        self.config.url = url.strip().rstrip("/")
        self.config.token = token.strip()
        self.config.save()
        self.api = ApiClient(base_url=self.config.url, token=self.config.token)

    def action_cycle_theme(self) -> None:
        """Switch between the three themes."""
        order = list(THEMES)
        index = order.index(self.theme) if self.theme in order else 0
        self.theme = order[(index + 1) % len(order)]

    def action_toggle_fullscreen(self) -> None:
        """Show the text in the whole screen, or shrink it back."""
        screen = self.screen
        if hasattr(screen, "toggle_fullscreen"):
            screen.toggle_fullscreen()

    def action_help(self) -> None:
        """Show the key bindings."""
        self.notify(
            "hjkl 移动 · ←→ 换句 · gg/G 章首末 · Ctrl+d/u 半页 · / 搜索 · "
            "Space 听书 · [ ] 换章 · s 同步 · S 拉取 · f 全屏 · m 主题 · q 返回",
            title="快捷键",
            timeout=8,
        )

    def on_exit(self) -> None:
        self.audio.cleanup()


def main() -> None:
    """Entry point of the terminal client."""
    LectorApp().run()


if __name__ == "__main__":
    main()
