"""Pydantic contracts shared by the application service and local API."""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    NonNegativeInt,
    PositiveFloat,
    PositiveInt,
    model_validator,
)

from vibesound.audio.types import AudioBackendSnapshot
from vibesound.engine.types import EngineSnapshot
from vibesound.rendering.types import RenderCommand, RenderOperation, RenderRequest


class APIModel(BaseModel):
    """Reject unknown fields so API contracts cannot silently drift."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SetOperation(APIModel):
    op: Literal["set"]
    path: str = Field(min_length=2)
    value: Any


class TransactionRequest(APIModel):
    base_revision: NonNegativeInt
    operations: list[SetOperation] = Field(min_length=1)


class ApiIssue(APIModel):
    code: str
    path: str = ""
    message: str


class TransactionResult(APIModel):
    ok: bool
    committed: bool
    base_revision: NonNegativeInt
    before_revision: NonNegativeInt
    after_revision: NonNegativeInt
    current_revision: NonNegativeInt
    changed_paths: list[str] = Field(default_factory=list)
    errors: list[ApiIssue] = Field(default_factory=list)


class EngineSnapshotModel(APIModel):
    mode: str
    position_frame: NonNegativeInt
    active_clip_ids: list[tuple[UUID, UUID]]
    pending_action_frames: list[NonNegativeInt]

    @classmethod
    def from_snapshot(cls, snapshot: EngineSnapshot) -> "EngineSnapshotModel":
        return cls(
            mode=snapshot.mode.value,
            position_frame=snapshot.position_frame,
            active_clip_ids=list(snapshot.active_clip_ids),
            pending_action_frames=list(snapshot.pending_action_frames),
        )


class AudioDeviceModel(APIModel):
    index: NonNegativeInt
    name: str
    host_api: str
    max_output_channels: PositiveInt
    default_sample_rate: PositiveFloat


class AudioErrorModel(APIModel):
    code: str
    message: str
    recoverable: bool


class AudioSnapshotModel(APIModel):
    state: str
    device: AudioDeviceModel | None
    underrun_count: NonNegativeInt
    last_error: AudioErrorModel | None

    @classmethod
    def from_snapshot(cls, snapshot: AudioBackendSnapshot) -> "AudioSnapshotModel":
        device = snapshot.device
        error = snapshot.last_error
        return cls(
            state=snapshot.state.value,
            device=(
                None
                if device is None
                else AudioDeviceModel(
                    index=device.index,
                    name=device.name,
                    host_api=device.host_api,
                    max_output_channels=device.max_output_channels,
                    default_sample_rate=device.default_sample_rate,
                )
            ),
            underrun_count=snapshot.underrun_count,
            last_error=(
                None
                if error is None
                else AudioErrorModel(
                    code=error.code,
                    message=error.message,
                    recoverable=error.recoverable,
                )
            ),
        )


class ApplicationSnapshot(APIModel):
    project_id: UUID
    revision: NonNegativeInt
    engine: EngineSnapshotModel
    audio: AudioSnapshotModel


TransportOperation = Literal["play", "pause", "stop", "reset"]


class TransportRequest(APIModel):
    operation: TransportOperation


class ClipLaunchRequest(APIModel):
    track_id: UUID
    scene_id: UUID


class ClipStopRequest(APIModel):
    track_id: UUID


class RenderCommandRequest(APIModel):
    frame: NonNegativeInt
    operation: RenderOperation
    track_id: UUID | None = None
    scene_id: UUID | None = None

    @model_validator(mode="after")
    def validate_command_arguments(self) -> "RenderCommandRequest":
        if self.operation == "launch_slot":
            if self.track_id is None or self.scene_id is None:
                raise ValueError("launch_slot requires track_id and scene_id")
        elif self.operation == "launch_scene":
            if self.scene_id is None or self.track_id is not None:
                raise ValueError("launch_scene requires scene_id and no track_id")
        elif self.operation == "stop_track":
            if self.track_id is None or self.scene_id is not None:
                raise ValueError("stop_track requires track_id and no scene_id")
        elif self.track_id is not None or self.scene_id is not None:
            raise ValueError("stop_all does not accept track_id or scene_id")
        return self

    def to_domain(self) -> RenderCommand:
        return RenderCommand(
            frame=self.frame,
            operation=self.operation,
            track_id=self.track_id,
            scene_id=self.scene_id,
        )


class RenderJobRequest(APIModel):
    output_path: str = Field(min_length=1)
    bars: PositiveInt | None = None
    seconds: PositiveFloat | None = None
    commands: list[RenderCommandRequest] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_duration_and_order(self) -> "RenderJobRequest":
        if (self.bars is None) == (self.seconds is None):
            raise ValueError("Specify exactly one of bars or seconds")
        frames = [command.frame for command in self.commands]
        if frames != sorted(frames):
            raise ValueError("Render commands must be ordered by nondecreasing frame")
        return self

    def to_domain(self) -> RenderRequest:
        return RenderRequest(
            bars=self.bars,
            seconds=self.seconds,
            commands=tuple(command.to_domain() for command in self.commands),
        )


class EventEnvelope(APIModel):
    type: str
    project_id: UUID
    revision: NonNegativeInt
    payload: dict[str, Any] = Field(default_factory=dict)
