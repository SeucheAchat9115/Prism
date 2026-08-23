"""Immutable configuration, device, state, and diagnostic values."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite
from typing import Literal, TypeAlias

from vibesound.engine.types import EngineSnapshot


class AudioBackendState(StrEnum):
    """Lifecycle state visible to backend callers."""

    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    FAULTED = "faulted"
    CLOSED = "closed"


@dataclass(frozen=True, slots=True)
class AudioDeviceInfo:
    """A stereo-capable output device discovered through PortAudio."""

    index: int
    name: str
    host_api: str
    max_output_channels: int
    default_sample_rate: float

    def __post_init__(self) -> None:
        if not isinstance(self.index, int) or isinstance(self.index, bool) or self.index < 0:
            raise ValueError("Audio device index must be a non-negative integer")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("Audio device name must not be empty")
        if not isinstance(self.host_api, str) or not self.host_api.strip():
            raise ValueError("Audio device host API must not be empty")
        if (
            not isinstance(self.max_output_channels, int)
            or isinstance(self.max_output_channels, bool)
            or self.max_output_channels <= 0
        ):
            raise ValueError("Audio device output channel count must be positive")
        if not isfinite(float(self.default_sample_rate)) or self.default_sample_rate <= 0:
            raise ValueError("Audio device default sample rate must be positive and finite")


@dataclass(frozen=True, slots=True)
class AudioBackendConfig:
    """PortAudio stream settings with conservative Windows defaults."""

    device: int | str | None = None
    block_size: int = 512
    queue_blocks: int = 4
    sample_rate: int | None = None
    control_timeout_seconds: float = 2.0
    underrun_fault_count: int = 8
    underrun_window_seconds: float = 5.0

    def __post_init__(self) -> None:
        if self.device is not None and (
            isinstance(self.device, bool) or not isinstance(self.device, (int, str))
        ):
            raise ValueError("device must be an integer index, name, or None")
        if (
            not isinstance(self.block_size, int)
            or isinstance(self.block_size, bool)
            or self.block_size <= 0
        ):
            raise ValueError("block_size must be a positive integer")
        if not isinstance(self.queue_blocks, int) or isinstance(self.queue_blocks, bool):
            raise ValueError("queue_blocks must be an integer")
        if self.queue_blocks < 2:
            raise ValueError("queue_blocks must be at least 2")
        if self.sample_rate is not None and (
            not isinstance(self.sample_rate, int)
            or isinstance(self.sample_rate, bool)
            or self.sample_rate <= 0
        ):
            raise ValueError("sample_rate must be a positive integer when provided")
        if (
            not isinstance(self.control_timeout_seconds, (int, float))
            or isinstance(self.control_timeout_seconds, bool)
            or not isfinite(float(self.control_timeout_seconds))
            or self.control_timeout_seconds <= 0
        ):
            raise ValueError("control_timeout_seconds must be positive and finite")
        if (
            not isinstance(self.underrun_fault_count, int)
            or isinstance(self.underrun_fault_count, bool)
            or self.underrun_fault_count <= 0
        ):
            raise ValueError("underrun_fault_count must be a positive integer")
        if (
            not isinstance(self.underrun_window_seconds, (int, float))
            or isinstance(self.underrun_window_seconds, bool)
            or not isfinite(float(self.underrun_window_seconds))
            or self.underrun_window_seconds <= 0
        ):
            raise ValueError("underrun_window_seconds must be positive and finite")


@dataclass(frozen=True, slots=True)
class AudioErrorInfo:
    """A stable diagnostic retained after a backend fault."""

    code: str
    message: str
    recoverable: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.code, str) or not self.code.strip():
            raise ValueError("Audio error code must not be empty")
        if not isinstance(self.message, str) or not self.message.strip():
            raise ValueError("Audio error message must not be empty")


@dataclass(frozen=True, slots=True)
class AudioBackendSnapshot:
    """A thread-safe diagnostic snapshot of device and engine state."""

    state: AudioBackendState
    engine_snapshot: EngineSnapshot
    device: AudioDeviceInfo | None
    underrun_count: int
    last_error: AudioErrorInfo | None
    queued_latency_frames: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.state, AudioBackendState):
            raise ValueError("state must be an AudioBackendState")
        if not isinstance(self.underrun_count, int) or self.underrun_count < 0:
            raise ValueError("underrun_count must be a non-negative integer")
        if not isinstance(self.queued_latency_frames, int) or self.queued_latency_frames < 0:
            raise ValueError("queued_latency_frames must be a non-negative integer")


AudioCommandName: TypeAlias = Literal[
    "play",
    "pause",
    "stop",
    "reset",
    "launch_slot",
    "launch_scene",
    "stop_track",
    "stop_all",
    "update_mixer",
    "replace_project",
    "drain_events",
]
