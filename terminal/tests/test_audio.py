"""The displayed rate must be the rate passed to the real audio backend."""
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest


@pytest.mark.parametrize("backend,flag", [("afplay", "-r"), ("ffplay", "-af"), ("mpv", "--speed=1.75")])
def test_native_speed_without_ffmpeg(monkeypatch, backend, flag):
    from lector_tui.audio import AudioPlayer
    calls = []
    monkeypatch.setattr("lector_tui.audio.shutil.which", lambda name: None)
    monkeypatch.setattr("lector_tui.audio.subprocess.Popen", lambda args, **kw: calls.append(args) or SimpleNamespace(poll=lambda: 0))
    player = AudioPlayer(backend=backend, rate=1.75)
    player.play("sentence.mp3")
    assert flag in calls[0]
    assert player.effective_rate == 1.75
    assert calls[0][-1] == "sentence.mp3"
    if backend == "afplay":
        assert calls[0][calls[0].index("-r") + 1] == "1.75"
    if backend == "ffplay":
        assert calls[0][calls[0].index("-af") + 1] == "atempo=1.75"


def test_aplay_does_not_silently_ignore_speed(monkeypatch):
    from lector_tui.audio import AudioPlayer
    monkeypatch.setattr("lector_tui.audio.shutil.which", lambda name: None)
    with pytest.raises(RuntimeError, match="ffmpeg"):
        AudioPlayer(backend="aplay", rate=1.5).play("sentence.mp3")


def test_audio_and_word_timings_use_identical_voice_and_synthesis_rate(monkeypatch):
    from lector_tui.api import ApiClient
    client = ApiClient("https://example.test/ebook")
    requests = []
    monkeypatch.setattr(client, "request", lambda path, params=None: requests.append((path, params)))
    url = client.audio_url("a", "c0.b0.s0", voice_id="en-female", rate="-8%")
    client.get_words("a", "c0.b0.s0", voice_id="en-female", rate="-8%")
    params = parse_qs(urlparse(url).query)
    assert params == {key: [value] for key, value in requests[0][1].items()}
    assert params == {"voice_id": ["en-female"], "rate": ["-8%"]}
