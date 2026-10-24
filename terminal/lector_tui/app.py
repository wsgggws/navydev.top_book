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
        border-right: solid $panel;
        overflow-y: auto;
    }

    #text-pane {
        width: 1fr;
        overflow-y: auto;
        padding: 0 2;
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
        ("question_mark", "help", "帮助"),
    ]

    def __init__(self, base_url: str | None = None, token: str | None = None) -> None:
        super().__init__()
        self.api = ApiClient(
            base_url=base_url or os.environ.get("LECTOR_URL", "http://127.0.0.1:8000"),
            token=token or os.environ.get("LECTOR_TOKEN", ""),
        )
        self.audio = AudioPlayer()
        for theme in THEMES.values():
            self.register_theme(theme)
        self.theme = os.environ.get("LECTOR_THEME", "paper")
        if self.theme not in THEMES:
            self.theme = "paper"

    def on_mount(self) -> None:
        self.push_screen(LibraryScreen())

    def action_cycle_theme(self) -> None:
        """Switch between the three themes."""
        order = list(THEMES)
        index = order.index(self.theme) if self.theme in order else 0
        self.theme = order[(index + 1) % len(order)]

    def action_help(self) -> None:
        """Show the key bindings."""
        self.notify(
            "↑↓ 滚动 · ←→ 上一句/下一句 · Space 听书 · [ ] 换章 · s 同步进度 · "
            "S 拉取进度 · m 主题 · q 返回",
            title="快捷键",
            timeout=6,
        )

    def on_exit(self) -> None:
        self.audio.cleanup()


def main() -> None:
    """Entry point of the terminal client."""
    LectorApp().run()


if __name__ == "__main__":
    main()
