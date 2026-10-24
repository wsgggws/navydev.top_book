"""MP3 duration and trimming from frame headers.

The synthesisers do not report a duration, but the browser needs one to know
when a tile ends.  Reading the frame headers is enough and needs no decoder.

The same frames let us cut the silence that surrounds the speech: every
synthesised tile starts with a short lead-in and ends with a short tail, and
concatenating those tiles as they are would leave a pause between every
sentence.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Bitrates in kbit/s for Layer III.
_BITRATE_MPEG1 = (0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320)
_BITRATE_MPEG2 = (0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160)

_SAMPLE_RATES = {
    3: (44100, 48000, 32000),   # MPEG 1
    2: (22050, 24000, 16000),   # MPEG 2
    0: (11025, 12000, 8000),    # MPEG 2.5
}

_SAMPLES_PER_FRAME = {
    1: 384,   # Layer I
    2: 1152,  # Layer II
    3: None,  # Layer III, depends on the MPEG version
}


def _skip_id3(data: bytes) -> int:
    """Return the offset of the first frame after an ID3v2 tag."""
    if len(data) >= 10 and data[:3] == b"ID3":
        size = 0
        for byte in data[6:10]:
            size = (size << 7) | (byte & 0x7F)
        return 10 + size
    return 0


def mp3_duration(data: bytes) -> float:
    """Duration of an MP3 stream in seconds, or ``0.0`` when unreadable."""
    offset = _skip_id3(data)
    total_samples = 0
    sample_rate = 0
    length = len(data)
    while offset + 4 <= length:
        header = data[offset : offset + 4]
        if header[0] != 0xFF or (header[1] & 0xE0) != 0xE0:
            offset += 1
            continue
        version_bits = (header[1] >> 3) & 0x03
        layer_bits = (header[1] >> 1) & 0x03
        bitrate_index = (header[2] >> 4) & 0x0F
        rate_index = (header[2] >> 2) & 0x03
        padding = (header[2] >> 1) & 0x01
        if version_bits == 1 or layer_bits == 0:
            offset += 1
            continue
        if bitrate_index in (0, 15) or rate_index == 3:
            offset += 1
            continue
        layer = 4 - layer_bits
        table = _BITRATE_MPEG1 if version_bits == 3 else _BITRATE_MPEG2
        bitrate = table[bitrate_index] * 1000
        rate = _SAMPLE_RATES[version_bits][rate_index]
        if layer == 3:
            samples = 1152 if version_bits == 3 else 576
            frame_size = (144 if version_bits == 3 else 72) * bitrate // rate + padding
        elif layer == 2:
            samples = 1152
            frame_size = 144 * bitrate // rate + padding
        else:
            samples = 384
            frame_size = (12 * bitrate // rate + padding) * 4
        if frame_size <= 4:
            offset += 1
            continue
        total_samples += samples
        sample_rate = sample_rate or rate
        offset += frame_size
    if not sample_rate or not total_samples:
        return 0.0
    return total_samples / sample_rate


@dataclass
class Frame:
    """One MP3 frame."""

    offset: int
    size: int
    start: float
    duration: float


def iter_frames(data: bytes) -> list[Frame]:
    """Every frame of the stream, with its position in time."""
    frames: list[Frame] = []
    offset = _skip_id3(data)
    length = len(data)
    clock = 0.0
    sample_rate = 0
    while offset + 4 <= length:
        header = data[offset : offset + 4]
        if header[0] != 0xFF or (header[1] & 0xE0) != 0xE0:
            offset += 1
            continue
        version_bits = (header[1] >> 3) & 0x03
        layer_bits = (header[1] >> 1) & 0x03
        bitrate_index = (header[2] >> 4) & 0x0F
        rate_index = (header[2] >> 2) & 0x03
        padding = (header[2] >> 1) & 0x01
        if version_bits == 1 or layer_bits == 0:
            offset += 1
            continue
        if bitrate_index in (0, 15) or rate_index == 3:
            offset += 1
            continue
        layer = 4 - layer_bits
        table = _BITRATE_MPEG1 if version_bits == 3 else _BITRATE_MPEG2
        bitrate = table[bitrate_index] * 1000
        rate = _SAMPLE_RATES[version_bits][rate_index]
        if layer == 3:
            samples = 1152 if version_bits == 3 else 576
            frame_size = (144 if version_bits == 3 else 72) * bitrate // rate + padding
        elif layer == 2:
            samples = 1152
            frame_size = 144 * bitrate // rate + padding
        else:
            samples = 384
            frame_size = (12 * bitrate // rate + padding) * 4
        if frame_size <= 4:
            offset += 1
            continue
        sample_rate = sample_rate or rate
        duration = samples / sample_rate
        frames.append(
            Frame(offset=offset, size=frame_size, start=clock, duration=duration)
        )
        clock += duration
        offset += frame_size
    return frames


def trim_mp3(data: bytes, start: float, end: float | None = None) -> tuple[bytes, float, float]:
    """Cut the silence around the speech.

    Returns the trimmed audio, how much time was cut from the front and the
    duration of what is left.  Frames that hold no speech are dropped, the
    ones that carry the first and last word are kept whole.
    """
    frames = iter_frames(data)
    if not frames:
        return data, 0.0, mp3_duration(data)
    first = 0
    for index, frame in enumerate(frames):
        if frame.start + frame.duration > start:
            first = index
            break
    last = len(frames) - 1
    if end is not None:
        for index in range(len(frames) - 1, -1, -1):
            if frames[index].start < end:
                last = index
                break
    if last < first:
        return data, 0.0, mp3_duration(data)
    shift = frames[first].start
    head = data[: frames[first].offset]
    body = data[frames[first].offset : frames[last].offset + frames[last].size]
    trimmed = head + body
    duration = frames[last].start + frames[last].duration - shift
    return trimmed, shift, duration
