"""Small deterministic media fixtures for project persistence tests."""

from __future__ import annotations

import math
import wave
from pathlib import Path


def write_wav(path: Path, *, frames: int = 64, sample_rate: int = 8000) -> bytes:
    samples = bytearray()
    for index in range(frames):
        value = int(12000 * math.sin(2 * math.pi * index / frames))
        samples.extend(value.to_bytes(2, byteorder="little", signed=True))
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        audio.writeframes(bytes(samples))
    return path.read_bytes()
