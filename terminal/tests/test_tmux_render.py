"""Render cached images through an isolated tmux server and an outer terminal PTY."""
import fcntl
import base64
from io import BytesIO
import json
import os
import pty
import re
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
@pytest.mark.parametrize("outer,passthrough", [("WezTerm", True), ("WezTerm", False), ("foot", False)])
def test_real_tmux_preserves_cached_images_with_native_support_or_fallback(tmp_path, advertised, outer, passthrough):
    from lector_tui.cache import ImageCache

    cache_root = tmp_path / "cache"
    data = BytesIO()
    picture = Image.new("RGB", (200, 160))
    picture.putdata([(x, y, (x + y) % 256) for y in range(160) for x in range(200)])
    picture.save(data, format="PNG")
    assert ImageCache(cache_root / "images", namespace="test").put("book", "cover", data.getvalue())
    socket = "lector-test-" + uuid.uuid4().hex[:10]
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 30, 100, 1000, 600))
    env = dict(os.environ, TERM="xterm-256color", TERM_PROGRAM=outer,
               LECTOR_CACHE_DIR=str(cache_root))
    env.pop("WEZTERM_PANE", None)
    if outer == "WezTerm":
        # tmux may replace TERM_PROGRAM; WezTerm's pane identity survives.
        env.update(TERM_PROGRAM="tmux", WEZTERM_PANE="test")
    env.pop("TMUX", None)
    marker = tmp_path / "rendered.json"
    config = tmp_path / "tmux.conf"
    config.write_text("set -g allow-passthrough on\n" if passthrough else "")
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
                self.set_timer(.2, lambda: setattr(self.query_one(TerminalImage), "image", BytesIO(data)))
                self.set_timer(1.0, self.exit)
        Demo().run()
    '''))
    shell = shlex.join([sys.executable, str(script), str(marker)])
    process = subprocess.Popen(
        ["tmux", "-vv", "-L", socket, "-f", str(config), "new-session", "-s", "repro", shell],
        stdin=slave, stdout=slave, stderr=slave, env=env, cwd=tmp_path,
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
        expected_native = advertised and report["built"] == "1" and outer != "WezTerm"
        assert report["sixel"] == expected_native
        if outer == "WezTerm" and passthrough:
            packets = re.findall(rb"\x1b_G([^;\x1b]*);([A-Za-z0-9+/=]*)\x1b\\", output)
            pngs, chunks = [], []
            for header, data in packets:
                assert b"q=2" in header, "graphics must not leave replies in shell input"
                if b"a=T" in header:
                    chunks = []
                    assert b"f=100" in header
                chunks.append(data)
                if b"m=0" in header:
                    pngs.append(base64.b64decode(b"".join(chunks)))
            assert len(pngs) >= 2, "initial and async image must use high-resolution PNG, not half cells"
            image = Image.open(BytesIO(pngs[-1]))
            assert image.width >= 200 and image.height >= 160
            assert len(image.getcolors(maxcolors=100_000) or []) > 256
        elif expected_native:
            assert b'"1;1;' in output, "tmux must pass native image pixels to the outer terminal"
            assert len(set(re.findall(rb"#[0-9]+;2;[0-9;]+", output))) > 16
            # tmux retains native images independently of Textual's blank text
            # cells. Replacing a bitmap must release the old layer, even when
            # the compositor elides the unchanged spaces beneath it.
            log = next(tmp_path.glob("tmux-server-*.log")).read_text(errors="replace")
            live = peak = stored = 0
            for event in re.findall(r"\bimage_(store|free):", log):
                if event == "store":
                    live += 1
                    stored += 1
                    peak = max(peak, live)
                else:
                    live -= 1
            assert stored >= 2, "exercise asynchronous bitmap replacement"
            assert peak == 1, "repainting one widget must not stack old tmux image layers"
        else:
            assert "▀".encode() in output, "tmux must display color halfcells instead of blank images"
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        subprocess.run(["tmux", "-L", socket, "kill-server"], capture_output=True)
        os.close(master)
