"""Find where each beat is spoken inside one continuous PCM take."""
from __future__ import annotations

import io
import wave
from typing import List, Tuple

import numpy as np

PCM_RATE = 24000
PCM_SAMPLE_WIDTH = 2
# Shortest silence that counts as a pause between sentences.
MIN_PAUSE_SEC = 0.15
# How far (as a fraction of the average beat length) a beat boundary may sit
# from its text-share estimate when snapping to a real pause.
BOUNDARY_TOLERANCE = 0.35


def find_pauses(pcm: bytes) -> List[Tuple[float, float]]:
    """(start, end) seconds of every silent stretch of at least MIN_PAUSE_SEC."""
    samples = np.frombuffer(pcm, dtype="<i2").astype(np.float32)
    frame = PCM_RATE // 100
    count = len(samples) // frame
    if count == 0:
        return []
    rms = np.sqrt((samples[:count * frame].reshape(count, frame) ** 2).mean(axis=1))
    quiet = rms < max(float(rms.max()) * 0.03, 1.0)
    pauses = []
    run_start = None
    for index, is_quiet in enumerate(list(quiet) + [False]):
        if is_quiet and run_start is None:
            run_start = index
        elif not is_quiet and run_start is not None:
            if (index - run_start) / 100 >= MIN_PAUSE_SEC:
                pauses.append((run_start / 100, index / 100))
            run_start = None
    return pauses


def locate_beats(pcm: bytes, beats: List[str]) -> List[List[float]]:
    """Find where each beat is spoken in one continuous take.

    Each boundary is first estimated from the beats' share of the text, then
    snapped to the longest real pause near that estimate (sentence breaks are
    the longest pauses). With no pause nearby the estimate is kept.
    """
    total = len(pcm) / (PCM_RATE * PCM_SAMPLE_WIDTH)
    chars = [max(len(text.strip()), 1) for text in beats]
    tolerance = BOUNDARY_TOLERANCE * total / len(beats)
    pauses = [p for p in find_pauses(pcm) if p[0] > 0 and p[1] < total - 0.01]

    windows = []
    start = 0.0
    spoken = 0
    for count in chars[:-1]:
        spoken += count
        expected = total * spoken / sum(chars)
        nearby = [
            p for p in pauses
            if p[0] > start and abs((p[0] + p[1]) / 2 - expected) <= tolerance
        ]
        pause = max(nearby, key=lambda p: p[1] - p[0]) if nearby else (expected, expected)
        windows.append([round(start, 3), round(pause[0], 3)])
        start = pause[1]
    windows.append([round(start, 3), round(total, 3)])
    return windows


def pcm_to_wav(pcm: bytes, *, channels: int = 1, sample_width: int = PCM_SAMPLE_WIDTH, rate: int = PCM_RATE) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(rate)
        wav_file.writeframes(pcm)
    return buf.getvalue()
