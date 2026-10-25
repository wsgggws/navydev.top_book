"""A real PTY catches late graphics responses leaking back to the shell."""

import os
import select
import subprocess
import sys
import time

import pytest


def boot_in_terminal(args, *, program="WezTerm", zero_size=False):
    import fcntl
    import pty
    import struct
    import termios

    master, slave = pty.openpty()
    size = (0, 0, 0, 0) if zero_size else (30, 80, 800, 600)
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", *size))
    env = dict(os.environ, TERM="xterm-256color", TERM_PROGRAM=program)
    for name in ("WEZTERM_PANE", "KITTY_WINDOW_ID", "TMUX"):
        env.pop(name, None)
    if program == "kitty":
        env["TERM"] = "xterm-kitty"
    code = (
        "from lector_tui import app; import time; "
        "app.LectorApp.run=lambda self: print('UI_READY',flush=True); "
        f"app.main({args!r}); time.sleep(.1)"
    )
    process = subprocess.Popen([sys.executable, "-c", code], stdin=slave, stdout=slave, stderr=slave, env=env)
    os.close(slave)
    output = b""
    answered = set()
    late = None
    deadline = time.monotonic() + 5
    try:
        while time.monotonic() < deadline:
            if late is not None and time.monotonic() >= late:
                # Deliberately arrive after primary DA, as some terminals do.
                os.write(master, b"\x1b_Gi=12345;OK\x1b\\")
                late = None
            if not select.select([master], [], [], .01)[0]:
                if process.poll() is not None:
                    break
                continue
            try:
                chunk = os.read(master, 65536)
            except OSError:
                break
            if not chunk:
                break
            output += chunk
            if b"\x1b[c" in output and "da" not in answered:
                os.write(master, b"\x1b[?62;4c")
                answered.add("da")
                if b"\x1b_G" in output:
                    late = time.monotonic() + .025
            if b"\x1b[16t" in output and "cell" not in answered:
                os.write(master, b"\x1b[6;20;10t")
                answered.add("cell")
            for query, reply in [
                (b"\x1b]10;?\x07", b"\x1b]10;rgb:eeee/eeee/eeee\x1b\\"),
                (b"\x1b]11;?\x07", b"\x1b]11;rgb:2222/2222/2222\x1b\\"),
                (b"\x1b]4;4;?\x07", b"\x1b]4;4;rgb:5555/7777/aaaa\x1b\\"),
            ]:
                if query in output and query not in answered:
                    os.write(master, reply)
                    answered.add(query)
        process.wait(timeout=1)
        return process.returncode, output
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        os.close(master)


@pytest.mark.parametrize("program", ["WezTerm", "kitty", "unknown"])
def test_startup_never_sends_a_kitty_query_or_leaks_its_late_reply(program):
    code, output = boot_in_terminal(["--theme", "night"], program=program)
    assert code == 0 and b"UI_READY" in output, repr(output)
    assert b"\x1b_G" not in output, "Kitty capability queries can leave late replies in shell input"
    assert b"^[_G" not in output and b";OK" not in output, repr(output)


def test_new_terminal_with_zero_ioctl_dimensions_still_starts():
    code, output = boot_in_terminal(["--theme", "night"], zero_size=True)
    assert code == 0 and b"UI_READY" in output, repr(output)


@pytest.mark.parametrize("option", ["--version", "--help"])
def test_one_shot_commands_emit_no_probe_even_in_a_real_tty(option):
    code, output = boot_in_terminal([option])
    assert code == 0
    assert b"\x1b" not in output and b"^[_G" not in output, repr(output)
