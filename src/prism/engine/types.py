"""Immutable runtime values and typed events emitted by the engine."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, TypeAlias
from uuid import UUID

import numpy as np
from numpy.typing import NDArray

Float32Array: TypeAlias = NDArray[np.float32]


class TransportMode(StrEnum):
    """The runtime playback mode, which is intentionally not persisted."""

    STOPPED = "stopped"
    PAUSED = "paused"
    PLAYING = "playing"


@dataclass(frozen=True, slots=True)
class TransportChangedEvent:
    """A transport mode or position change."""

    frame: int
    mode: TransportMode
    position_frame: int
    kind: Literal["transport.changed"] = "transport.changed"


@dataclass(frozen=True, slots=True)
class ClipLaunchedEvent:
    """A clip became active on a track."""

    frame: int
    track_id: UUID
    scene_id: UUID
    clip_id: UUID
    kind: Literal["clip.launched"] = "clip.launched"


@dataclass(frozen=True, slots=True)
class ClipStoppedEvent:
    """A clip stopped because of a command, replacement, or natural completion."""

    frame: int
    track_id: UUID
    scene_id: UUID
    clip_id: UUID
    kind: Literal["clip.stopped"] = "clip.stopped"


@dataclass(frozen=True, slots=True)
class ClipCompletedEvent(ClipStoppedEvent):
    """A non-looping clip reached the end of its playable source region."""

    kind: Literal["clip.stopped"] = "clip.stopped"


EngineEvent: TypeAlias = (
    TransportChangedEvent | ClipLaunchedEvent | ClipStoppedEvent | ClipCompletedEvent
)


@dataclass(frozen=True, slots=True)
class ScheduledAction:
    """The result of a session command that may be quantized."""

    target_frame: int
    affected_track_ids: tuple[UUID, ...]
    changed: bool


@dataclass(frozen=True, slots=True)
class EngineSnapshot:
    """Read-only runtime state useful to tests and future clients."""

    mode: TransportMode
    position_frame: int
    active_clip_ids: tuple[tuple[UUID, UUID], ...]
    pending_action_frames: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class EngineStep:
    """One deterministic engine advancement result."""

    start_frame: int
    end_frame: int
    samples: Float32Array
    events: tuple[EngineEvent, ...]


def empty_stereo_buffer(frames: int) -> Float32Array:
    """Return a correctly shaped silent stereo buffer."""

    return np.zeros((frames, 2), dtype=np.float32)
