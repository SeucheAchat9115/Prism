"""Immutable public contracts for deterministic offline rendering."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from math import isfinite
from pathlib import Path
from typing import Literal
from uuid import UUID

from vibesound.engine.clock import TransportClock
from vibesound.project.models import Project
from vibesound.rendering.errors import InvalidRenderRequestError

RenderOperation = Literal["launch_slot", "launch_scene", "stop_track", "stop_all"]
_OPERATIONS = frozenset(("launch_slot", "launch_scene", "stop_track", "stop_all"))


def _ceil_fraction(value: Fraction) -> int:
    return -((-value.numerator) // value.denominator)


def _require_uuid(value: UUID | None, name: str) -> None:
    if value is not None and not isinstance(value, UUID):
        raise InvalidRenderRequestError(f"{name} must be a UUID when provided")


@dataclass(frozen=True, slots=True)
class RenderCommand:
    """One exact-frame session command in an offline render."""

    frame: int
    operation: RenderOperation
    track_id: UUID | None = None
    scene_id: UUID | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.frame, int) or isinstance(self.frame, bool) or self.frame < 0:
            raise InvalidRenderRequestError("Render command frame must be a non-negative integer")
        if not isinstance(self.operation, str) or self.operation not in _OPERATIONS:
            raise InvalidRenderRequestError(
                f"Unsupported render command operation: {self.operation!r}"
            )
        _require_uuid(self.track_id, "track_id")
        _require_uuid(self.scene_id, "scene_id")

        if self.operation == "launch_slot":
            if self.track_id is None or self.scene_id is None:
                raise InvalidRenderRequestError(
                    "launch_slot commands require both track_id and scene_id"
                )
        elif self.operation == "launch_scene":
            if self.scene_id is None or self.track_id is not None:
                raise InvalidRenderRequestError(
                    "launch_scene commands require scene_id and no track_id"
                )
        elif self.operation == "stop_track":
            if self.track_id is None or self.scene_id is not None:
                raise InvalidRenderRequestError(
                    "stop_track commands require track_id and no scene_id"
                )
        elif self.track_id is not None or self.scene_id is not None:
            raise InvalidRenderRequestError("stop_all commands do not accept track_id or scene_id")


@dataclass(frozen=True, slots=True)
class RenderRequest:
    """A fixed render duration and an ordered sequence of exact-frame commands."""

    bars: int | None = None
    seconds: float | None = None
    commands: tuple[RenderCommand, ...] = ()

    def __post_init__(self) -> None:
        has_bars = self.bars is not None
        has_seconds = self.seconds is not None
        if has_bars == has_seconds:
            raise InvalidRenderRequestError("Specify exactly one of bars or seconds")
        if has_bars and (
            not isinstance(self.bars, int) or isinstance(self.bars, bool) or self.bars <= 0
        ):
            raise InvalidRenderRequestError("bars must be a positive integer")
        if has_seconds and (
            not isinstance(self.seconds, (int, float))
            or isinstance(self.seconds, bool)
            or not isfinite(float(self.seconds))
            or self.seconds <= 0
        ):
            raise InvalidRenderRequestError("seconds must be a positive finite number")

        try:
            commands = tuple(self.commands)
        except TypeError as exc:
            raise InvalidRenderRequestError(
                "commands must be an iterable of RenderCommand"
            ) from exc
        previous_frame = -1
        for index, command in enumerate(commands):
            if not isinstance(command, RenderCommand):
                raise InvalidRenderRequestError(
                    f"commands[{index}] must be a RenderCommand instance"
                )
            if command.frame < previous_frame:
                raise InvalidRenderRequestError(
                    "Render commands must be ordered by nondecreasing frame"
                )
            previous_frame = command.frame
        object.__setattr__(self, "commands", commands)

    def total_frames(self, project: Project) -> int:
        """Return the requested output length in project sample frames."""

        if not isinstance(project, Project):
            raise InvalidRenderRequestError("total_frames() requires a Project")
        if self.bars is not None:
            clock = TransportClock.from_transport(project.transport)
            return _ceil_fraction(Fraction(self.bars, 1) * clock.frames_per_bar)
        assert self.seconds is not None
        return _ceil_fraction(Fraction(str(self.seconds)) * project.transport.sample_rate)

    def frame_count(self, project: Project) -> int:
        """Alias for :meth:`total_frames` used by render callers."""

        return self.total_frames(project)


@dataclass(frozen=True, slots=True)
class RenderMetadata:
    """Metadata returned after an output file has been atomically committed."""

    project_id: UUID
    revision: int
    output_path: Path
    format: str
    subtype: str
    sample_rate: int
    channels: int
    frames: int
    duration_seconds: float

    def __post_init__(self) -> None:
        if not isinstance(self.project_id, UUID):
            raise ValueError("project_id must be a UUID")
        if (
            not isinstance(self.revision, int)
            or isinstance(self.revision, bool)
            or self.revision < 0
        ):
            raise ValueError("revision must be a non-negative integer")
        object.__setattr__(self, "output_path", Path(self.output_path))
        if not isinstance(self.format, str) or not self.format:
            raise ValueError("format must be a non-empty string")
        if not isinstance(self.subtype, str) or not self.subtype:
            raise ValueError("subtype must be a non-empty string")
        if not isinstance(self.sample_rate, int) or self.sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        if self.channels <= 0 or self.frames < 0 or self.duration_seconds < 0:
            raise ValueError("channels, frames, and duration_seconds must be non-negative")
