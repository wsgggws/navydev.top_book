"""Terminal colour-scheme detection.

Textual's ANSI themes inherit the terminal's own background, foreground and
16-colour palette.  That is what makes the client follow WezTerm schemes such
as Sheepskin, Dracula or Catppuccin instead of painting over them.
"""

from __future__ import annotations

import os
import re
import select
import sys
import time

_OSC11 = re.compile(rb"\x1b]11;rgba?:([0-9a-fA-F]{1,4})/([0-9a-fA-F]{1,4})/([0-9a-fA-F]{1,4})")


def resolve_theme(preference: str = "auto", *, probe: bool = False) -> str:
    """Resolve ``auto`` to the ANSI theme matching the terminal background."""
    preference = (preference or "auto").strip()
    if preference != "auto":
        return preference
    tone = terminal_background_tone(probe=probe)
    return "ansi-light" if tone == "light" else "ansi-dark"


def terminal_background_tone(*, probe: bool = True) -> str | None:
    """Return ``light``/``dark`` using an explicit override, OSC 11, or env."""
    override = os.environ.get("LECTOR_THEME_BACKGROUND", "").strip().lower()
    if override in {"light", "dark"}:
        return override

    if probe:
        rgb = _query_osc11_background()
        if rgb is not None:
            return "light" if _is_light(*rgb) else "dark"

    colorfgbg = os.environ.get("COLORFGBG", "").strip()
    if colorfgbg:
        try:
            background = int(colorfgbg.rsplit(";", 1)[-1])
        except ValueError:
            pass
        else:
            return "light" if background in {7, 15} or background >= 231 else "dark"
    return None


def _query_osc11_background(timeout: float = 0.12) -> tuple[int, int, int] | None:
    """Ask the terminal for its background colour without disturbing the shell."""
    if os.environ.get("TERM", "").lower() == "dumb":
        return None
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return None

    try:
        import termios
        import tty
    except ImportError:
        return None

    fd = sys.stdin.fileno()
    try:
        previous = termios.tcgetattr(fd)
    except termios.error:
        return None

    data = b""
    try:
        tty.setraw(fd)
        os.write(sys.stdout.fileno(), b"\x1b]11;?\x07")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            remaining = max(0.0, deadline - time.monotonic())
            ready, _, _ = select.select([fd], [], [], remaining)
            if not ready:
                break
            chunk = os.read(fd, 256)
            if not chunk:
                break
            data += chunk
            if b"\x07" in data or b"\x1b\\" in data:
                break
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, previous)

    match = _OSC11.search(data)
    if not match:
        return None
    return tuple(_scale_channel(value) for value in match.groups())  # type: ignore[return-value]


def _scale_channel(raw: bytes) -> int:
    value = int(raw, 16)
    maximum = (16 ** len(raw)) - 1
    return round(value * 255 / maximum)


def _is_light(red: int, green: int, blue: int) -> bool:
    def linear(value: int) -> float:
        channel = value / 255
        return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4

    luminance = 0.2126 * linear(red) + 0.7152 * linear(green) + 0.0722 * linear(blue)
    return luminance >= 0.5


_COLOR_REPLY = re.compile(
    rb"\x1b\](10|11|4;\d+);rgb:([0-9a-fA-F]{1,4})/([0-9a-fA-F]{1,4})/([0-9a-fA-F]{1,4})(?:\x07|\x1b\\)"
)


def parse_terminal_colors(data: bytes) -> dict[str, str]:
    """Read only well-formed RGB replies; never reuse terminal control bytes."""
    colors: dict[str, str] = {}
    names = {b"10": "foreground", b"11": "background", b"4;4": "accent"}
    for match in _COLOR_REPLY.finditer(data):
        name = names.get(match[1])
        if name:
            colors[name] = "#" + "".join(f"{_scale_channel(value):02x}" for value in match.groups()[1:])
    return colors


def query_terminal_colors(timeout: float = 0.15) -> dict[str, str]:
    """Snapshot terminal colours before Textual owns stdin.

    Explicit RGB avoids default ANSI colours becoming black during Textual's
    background blending and Sixel repainting. The terminal palette is unchanged.
    """
    if os.environ.get("TERM", "").lower() == "dumb" or not sys.stdin.isatty() or not sys.stdout.isatty():
        return {}
    try:
        import termios
        import tty

        fd = sys.stdin.fileno()
        previous = termios.tcgetattr(fd)
    except (ImportError, OSError, ValueError):
        return {}
    data = b""
    try:
        tty.setraw(fd)
        os.write(sys.stdout.fileno(), b"\x1b]10;?\x07\x1b]11;?\x07\x1b]4;4;?\x07")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and len(data) < 4096:
            ready, _, _ = select.select([fd], [], [], max(0, deadline - time.monotonic()))
            if not ready:
                break
            chunk = os.read(fd, 1024)
            if not chunk:
                break
            data += chunk
            if len(parse_terminal_colors(data)) == 3:
                break
    except OSError:
        return {}
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, previous)
    return parse_terminal_colors(data)
