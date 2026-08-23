"""Audio sink protocols used by deterministic tests."""

from __future__ import annotations

from typing import Protocol

import numpy as np

from prism.engine.types import Float32Array


class AudioSink(Protocol):
    """Consume already-rendered stereo float32 blocks."""

    def write(self, samples: Float32Array) -> None:
        """Consume one block without changing its sample values."""


class FakeAudioSink:
    """Collect blocks for tests without opening an audio device."""

    def __init__(self) -> None:
        self.blocks: list[Float32Array] = []

    def write(self, samples: Float32Array) -> None:
        array = np.asarray(samples)
        if array.dtype != np.dtype(np.float32) or array.ndim != 2 or array.shape[1] != 2:
            raise ValueError("FakeAudioSink expects a float32 stereo buffer")
        self.blocks.append(np.array(array, dtype=np.float32, order="C", copy=True))

    @property
    def frames_written(self) -> int:
        return sum(block.shape[0] for block in self.blocks)

    def render(self) -> Float32Array:
        if not self.blocks:
            return np.zeros((0, 2), dtype=np.float32)
        return np.concatenate(self.blocks, axis=0).astype(np.float32, copy=False)
