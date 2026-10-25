"""Offline synthesis must release processes after timeout or cancellation."""

from __future__ import annotations

import asyncio

import pytest

from lector.tts.base import TTSUnavailable
from lector.tts.espeak import EspeakEngine


class HungProcess:
    def __init__(self):
        self.returncode = None
        self.killed = False
        self.reaped = False
        self.started = asyncio.Event()
        self.finished = asyncio.Event()

    async def communicate(self):
        self.started.set()
        await self.finished.wait()
        self.reaped = True
        return b'', b''

    def kill(self):
        self.killed = True
        self.returncode = -9
        self.finished.set()


@pytest.mark.parametrize('conversion', [False, True])
@pytest.mark.parametrize('cancel', [False, True])
def test_timeout_or_cancel_kills_and_reaps_process(monkeypatch, tmp_path, conversion, cancel):
    async def scenario():
        proc = HungProcess()
        async def start(*args, **kwargs):
            return proc
        monkeypatch.setattr('lector.tts.espeak.asyncio.create_subprocess_exec', start)
        monkeypatch.setattr('lector.tts.espeak.shutil.which', lambda _: '/test/binary')
        engine = EspeakEngine(timeout=10 if cancel else 0.01)
        engine.binary = '/test/espeak'
        action = (engine._to_mp3(tmp_path / 'in.wav', tmp_path / 'out.mp3') if conversion
                  else engine.synth('文字; $(touch /tmp/should-not-exist)', 'en-US-GuyNeural'))
        task = asyncio.create_task(action)
        await proc.started.wait()
        if cancel:
            task.cancel()
        with pytest.raises(asyncio.CancelledError if cancel else TTSUnavailable):
            await task
        assert proc.killed
        assert proc.reaped
    asyncio.run(scenario())
