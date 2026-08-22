"""Injected, preloaded audio sources for deterministic engine processing."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

import numpy as np
from numpy.typing import NDArray

from vibesound.engine.errors import InvalidAudioBufferError, MissingAudioSourceError

Float32Array = NDArray[np.float32]


@dataclass(frozen=True, slots=True)
class AudioBuffer:
    """A validated, immutable view of a mono or stereo float32 source."""

    sample_rate: int
    samples: Float32Array

    def __post_init__(self) -> None:
        if not isinstance(self.sample_rate, int) or isinstance(self.sample_rate, bool):
            raise InvalidAudioBufferError("Audio sample_rate must be an integer")
        if self.sample_rate <= 0:
            raise InvalidAudioBufferError("Audio sample_rate must be positive")
        array = np.asarray(self.samples)
        if array.dtype != np.dtype(np.float32):
            raise InvalidAudioBufferError("Audio samples must have dtype float32")
        if array.ndim != 2:
            raise InvalidAudioBufferError("Audio samples must have shape (frames, channels)")
        if array.shape[0] <= 0:
            raise InvalidAudioBufferError("Audio samples must contain at least one frame")
        if array.shape[1] not in (1, 2):
            raise InvalidAudioBufferError("Audio samples must have one or two channels")
        if not np.isfinite(array).all():
            raise InvalidAudioBufferError("Audio samples must contain only finite values")
        normalized = np.array(array, dtype=np.float32, order="C", copy=True)
        normalized.setflags(write=False)
        object.__setattr__(self, "samples", normalized)


class ClipSourceProvider(Protocol):
    """Provide a fully loaded source for a project audio asset."""

    def get(self, asset_id: UUID) -> AudioBuffer:
        """Return the source associated with ``asset_id``."""


class InMemoryClipSourceProvider:
    """Simple source provider used by tests and future preloading callers."""

    def __init__(self, buffers: Mapping[UUID, AudioBuffer]) -> None:
        self._buffers = dict(buffers)

    def get(self, asset_id: UUID) -> AudioBuffer:
        try:
            return self._buffers[asset_id]
        except KeyError as exc:
            raise MissingAudioSourceError(f"No audio source for asset {asset_id}") from exc
