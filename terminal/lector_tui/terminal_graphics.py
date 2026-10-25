"""Choose image capabilities without sending Kitty queries to other terminals.

WezTerm can answer primary DA before a pending Kitty query. The library stops
reading at DA, so the late APC reply can be echoed by the shell. Only Kitty's
Unicode placement renderer needs Kitty support; identify it from its environment.
"""

from __future__ import annotations

import os
import re
import select
import subprocess
import sys
import time

_DA = re.compile(rb"\x1b\[\?([0-9;]*)c")
_CELL = re.compile(rb"\x1b\[6;(\d+);(\d+)t")


def _query_sixel(need_cell_size: bool, timeout: float = 0.2) -> tuple[bool, int, int]:
    import termios
    import tty

    fd = sys.__stdin__.fileno()
    original = termios.tcgetattr(fd)
    data = b""
    try:
        tty.setraw(fd)
        query = (b"\x1b[16t" if need_cell_size else b"") + b"\x1b[c"
        os.write(sys.__stdout__.fileno(), query)
        deadline = time.monotonic() + timeout
        while len(data) < 4096:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([fd], [], [], remaining)[0]:
                break
            chunk = os.read(fd, 1024)
            if not chunk:
                break
            data += chunk
            if _DA.search(data) and (not need_cell_size or _CELL.search(data)):
                break
    finally:
        termios.tcsetattr(fd, termios.TCSANOW, original)
    da, cell = _DA.search(data), _CELL.search(data)
    return (
        bool(da and b"4" in da[1].split(b";")),
        int(cell[2]) if cell else 0,
        int(cell[1]) if cell else 0,
    )


def _tmux_can_display_sixel() -> bool:
    """A compiled-in decoder is insufficient if the attached client lacks Sixel.

    Read only tmux's virtual-terminal metadata; never change user/server options.
    Unknown/older versions and detached clients use the visible text fallback.
    """
    pane = os.environ.get("TMUX_PANE", "")
    if not re.fullmatch(r"%[0-9]+", pane):
        return False
    try:
        result = subprocess.run(
            ["tmux", "display-message", "-p", "-t", pane,
             "#{sixel_support}\t#{client_termfeatures}"],
            capture_output=True, text=True, timeout=0.25, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    built, _, features = result.stdout.strip().partition("\t")
    return result.returncode == 0 and built == "1" and "sixel" in features.split(",")


def configure_graphics() -> None:
    """Seed textual-image's cached result before importing its renderers.

    Direct WezTerm/Kitty sessions need no graphic round trip. tmux must confirm
    its own Sixel capability: outer terminal environment variables do not prove
    that a multiplexer can render native graphics. An unknown terminal
    gets a bounded Sixel DA query, never a Kitty APC query. Non-TTY commands do
    no terminal I/O. Ioctl dimensions can be zero in a newly opened PTY.
    """
    from textual_image import _terminal

    if hasattr(_terminal.probe_terminal, "_result"):
        return
    width = height = 0
    sixel = kitty = False
    terminal = os.environ.get("TERM", "").lower()
    interactive = (
        terminal != "dumb" and sys.__stdin__ is not None and sys.__stdout__ is not None
        and sys.__stdin__.isatty() and sys.__stdout__.isatty()
    )
    if interactive:
        try:
            rows, columns, pixels_x, pixels_y = _terminal.get_tiocgwinsz()
            width = pixels_x // columns if columns else 0
            height = pixels_y // rows if rows else 0
        except (OSError, ValueError):
            pass
        multiplexed = bool(os.environ.get("TMUX")) or terminal.startswith(("tmux", "screen"))
        kitty = not multiplexed and (terminal == "xterm-kitty" or bool(os.environ.get("KITTY_WINDOW_ID")))
        sixel = not multiplexed and not kitty and (
            os.environ.get("TERM_PROGRAM", "").lower() == "wezterm"
            or bool(os.environ.get("WEZTERM_PANE"))
        )
        if not kitty and not sixel:
            try:
                sixel, queried_width, queried_height = _query_sixel(not (width and height))
                if sixel and os.environ.get("TMUX"):
                    sixel = _tmux_can_display_sixel()
                width = width or queried_width
                height = height or queried_height
            except (ImportError, OSError, ValueError):
                pass
    if not (width and height):
        try:
            width = int(os.environ.get("TEXTUAL_CELL_WIDTH", "10"))
            height = int(os.environ.get("TEXTUAL_CELL_HEIGHT", "20"))
        except ValueError:
            width, height = 10, 20
    cells = _terminal.CellSize(max(1, width), max(1, height))
    _terminal.probe_terminal._result = _terminal.TerminalCapabilities(cells, sixel=sixel, tgp=kitty)
