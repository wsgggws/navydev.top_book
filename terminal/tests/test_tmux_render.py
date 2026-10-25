"""Render cached images through an isolated tmux server and an outer terminal PTY."""
import fcntl
from io import BytesIO
import json
import os
import pty
import select
import shlex
import shutil
import struct
import subprocess
import sys
import termios
import textwrap
import time
import uuid

from PIL import Image
import pytest


@pytest.mark.skipif(not shutil.which("tmux"), reason="tmux executable is not installed")
@pytest.mark.parametrize("advertised", [False, True])
def test_real_tmux_preserves_cached_images_with_native_support_or_fallback(tmp_path, advertised):
    from lector_tui.cache import ImageCache

    cache_root = tmp_path / "cache"
    data = BytesIO()
    Image.new("RGB", (200, 160), "red").save(data, format="PNG")
    assert ImageCache(cache_root / "images", namespace="test").put("book", "cover", data.getvalue())
    socket = "lector-test-" + uuid.uuid4().hex[:10]
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 30, 100, 1000, 600))
    env = dict(os.environ, TERM="xterm-256color", TERM_PROGRAM="WezTerm", WEZTERM_PANE="test",
               LECTOR_CACHE_DIR=str(cache_root))
    env.pop("TMUX", None)
    marker = tmp_path / "rendered.json"
    script = tmp_path / "render.py"
    script.write_text(textwrap.dedent('''
        from io import BytesIO
        import json, subprocess, sys
        from pathlib import Path
        from lector_tui.cache import ImageCache
        from lector_tui.image_app import ImageApp
        from lector_tui.image_widget import TerminalImage
        from textual.app import ComposeResult
        from textual_image._terminal import probe_terminal
        data = ImageCache(namespace="test").get("book", "cover")
        assert data, "tmux must reuse the file cached outside tmux"
        class Demo(ImageApp):
            CSS = "TerminalImage {width: 20; height: 8;}"
            def compose(self) -> ComposeResult:
                yield TerminalImage(BytesIO(data))
            def on_mount(self):
                built = subprocess.run(["tmux", "display-message", "-p", "#{sixel_support}"],
                                       capture_output=True, text=True).stdout.strip()
                Path(sys.argv[1]).write_text(json.dumps({"sixel": probe_terminal().sixel, "built": built}))
                self.set_timer(1.0, self.exit)
        Demo().run()
    '''))
    shell = shlex.join([sys.executable, str(script), str(marker)])
    process = subprocess.Popen(
        ["tmux", "-L", socket, "-f", "/dev/null", "new-session", "-s", "repro", shell],
        stdin=slave, stdout=slave, stderr=slave, env=env,
    )
    os.close(slave)
    output = b""
    try:
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            if not select.select([master], [], [], .03)[0]:
                if process.poll() is not None:
                    break
                continue
            try:
                chunk = os.read(master, 262144)
            except OSError:
                break
            output += chunk
            for query, reply in [
                (b"\x1b[c", b"\x1b[?62;4c" if advertised else b"\x1b[?62;6c"),
                (b"\x1b[>0c", b"\x1b[>0;20261025;0c"),
                (b"\x1b[16t", b"\x1b[6;20;10t"),
                (b"\x1b]10;?\x07", b"\x1b]10;rgb:eeee/eeee/eeee\x1b\\"),
                (b"\x1b]11;?\x07", b"\x1b]11;rgb:2222/2222/2222\x1b\\"),
            ]:
                if query in chunk:
                    os.write(master, reply)
        process.wait(timeout=2)
        assert marker.exists(), repr(output[-3000:])
        report = json.loads(marker.read_text())
        expected_native = advertised and report["built"] == "1"
        assert report["sixel"] == expected_native
        if expected_native:
            assert b'"1;1;' in output, "tmux must pass native image pixels to the outer terminal"
        else:
            assert "▀".encode() in output, "tmux must display color halfcells instead of blank images"
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        subprocess.run(["tmux", "-L", socket, "kill-server"], capture_output=True)
        os.close(master)
