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

    @classmethod
    def from_prevalidated(
        cls,
        sample_rate: int,
        samples: Float32Array,
    ) -> "AudioBuffer":
        """Wrap an immutable cache mapping that was validated when it was written."""

        array = np.asarray(samples)
        if (
            not isinstance(sample_rate, int)
            or sample_rate <= 0
            or array.dtype != np.dtype(np.float32)
            or array.ndim != 2
            or array.shape[0] <= 0
            or array.shape[1] not in (1, 2)
            or not array.flags.c_contiguous
        ):
            raise InvalidAudioBufferError("Prevalidated audio cache has an invalid layout")
        array.setflags(write=False)
        value = object.__new__(cls)
        object.__setattr__(value, "sample_rate", sample_rate)
        object.__setattr__(value, "samples", array)
        return value


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
