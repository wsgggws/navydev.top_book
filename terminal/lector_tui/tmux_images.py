"""Read-only tmux geometry and PNG transport for WezTerm's inline images."""

from __future__ import annotations

from dataclasses import dataclass
import os
import re
import subprocess


@dataclass(frozen=True)
class PaneGeometry:
    left: int
    top: int
    width: int
    height: int


def pane_geometry() -> PaneGeometry | None:
    """Only pass graphics to a visible pane whose server permits passthrough.

    Include a top status bar in outer-terminal coordinates. A zoomed-out pane
    and a pane in an inactive window must never paint over the active window.
    All values come from tmux; nothing changes the user's server or config.
    """
    pane = os.environ.get("TMUX_PANE", "")
    if not os.environ.get("TMUX") or not re.fullmatch(r"%[0-9]+", pane):
        return None
    try:
        result = subprocess.run(
            ["tmux", "display-message", "-p", "-t", pane,
             "#{allow-passthrough}\t#{window_active}\t#{window_zoomed_flag}\t#{pane_active}"
             "\t#{pane_left}\t#{pane_top}\t#{pane_width}\t#{pane_height}"
             "\t#{status-position}\t#{status}"],
            capture_output=True, text=True, timeout=.25, check=False,
        )
        allowed, active, zoomed, selected, left, top, width, height, status, lines = result.stdout.strip().split("\t")
        if result.returncode or allowed not in {"on", "all"} or active != "1":
            return None
        if zoomed == "1" and selected != "1":
            return None
        left, top, width, height = map(int, (left, top, width, height))
        if status == "top":
            top += {"on": 1, "off": 0}.get(lines, int(lines) if lines.isdigit() else 0)
        if min(left, top) < 0 or not (0 < width <= 10000 and 0 < height <= 10000):
            return None
        return PaneGeometry(left, top, width, height)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def passthrough(sequence: str) -> str:
    """Quote ESC for tmux's DCS transport, preserving the outer cursor."""
    # Chunking Kitty's payload is insufficient if one outer DCS still contains
    # the entire PNG. tmux discards strings over input-buffer-size (often 1 MiB).
    # Keep each complete graphics packet in its own small transport envelope.
    packets = re.split(r"(?<=\x1b\\)(?=\x1b_G)", sequence)
    position = re.match(r"\x1b\[\d+;\d+H", sequence)
    prefix = position[0] if position else ""
    envelopes = []
    for index, packet in enumerate(packets):
        # tmux can restore its cursor between raw packets. Repeat the absolute
        # position so the final Kitty chunk places the image in the right cell.
        body = (prefix if index else "") + packet
        frame = "\x1b7\x1b[?2026h" + body + "\x1b[?2026l\x1b8"
        envelopes.append("\x1bPtmux;" + frame.replace("\x1b", "\x1b\x1b") + "\x1b\\")
    return "".join(envelopes)
