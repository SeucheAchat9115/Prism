"""Pydantic contracts shared by the application service and local API."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any, Literal
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

from prism.audio.types import AudioBackendSnapshot
from prism.engine.types import EngineSnapshot
from prism.rendering.types import RenderCommand, RenderOperation, RenderRequest


class APIModel(BaseModel):
    """Reject unknown fields so API contracts cannot silently drift."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class SetOperation(APIModel):
    op: Literal["set"]
    op_id: str | None = Field(default=None, min_length=1, max_length=128)
    path: str = Field(min_length=2)
    value: Any


class ProjectRenameOperation(APIModel):
    op: Literal["project.rename"]
    op_id: str | None = Field(default=None, min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=200)


class TrackCreateOperation(APIModel):
    op: Literal["track.create"]
    op_id: str | None = Field(default=None, min_length=1, max_length=128)
    track_id: UUID | None = None
    name: str = Field(min_length=1, max_length=200)
    order: NonNegativeInt | None = None


class TrackRenameOperation(APIModel):
    op: Literal["track.rename"]
    op_id: str | None = Field(default=None, min_length=1, max_length=128)
    track_id: UUID
    name: str = Field(min_length=1, max_length=200)


class TrackReorderOperation(APIModel):
    op: Literal["track.reorder"]
    op_id: str | None = Field(default=None, min_length=1, max_length=128)
    track_id: UUID
    order: NonNegativeInt


class TrackDeleteOperation(APIModel):
    op: Literal["track.delete"]
    op_id: str | None = Field(default=None, min_length=1, max_length=128)
    track_id: UUID
    cascade: bool = False


class SceneCreateOperation(APIModel):
    op: Literal["scene.create"]
    op_id: str | None = Field(default=None, min_length=1, max_length=128)
    scene_id: UUID | None = None
    name: str = Field(min_length=1, max_length=200)
    order: NonNegativeInt | None = None


class SceneRenameOperation(APIModel):
    op: Literal["scene.rename"]
    op_id: str | None = Field(default=None, min_length=1, max_length=128)
    scene_id: UUID
    name: str = Field(min_length=1, max_length=200)


class SceneReorderOperation(APIModel):
    op: Literal["scene.reorder"]
    op_id: str | None = Field(default=None, min_length=1, max_length=128)
    scene_id: UUID
    order: NonNegativeInt


class SceneDeleteOperation(APIModel):
    op: Literal["scene.delete"]
    op_id: str | None = Field(default=None, min_length=1, max_length=128)
    scene_id: UUID
    cascade: bool = False


class AssetImportOperation(APIModel):
    op: Literal["asset.import"]
    op_id: str | None = Field(default=None, min_length=1, max_length=128)
    upload_id: UUID
    asset_id: UUID | None = None


class AssetDeleteOperation(APIModel):
    op: Literal["asset.delete"]
    op_id: str | None = Field(default=None, min_length=1, max_length=128)
    asset_id: UUID
    cascade: bool = False


class ClipCreateOperation(APIModel):
    op: Literal["clip.create"]
    op_id: str | None = Field(default=None, min_length=1, max_length=128)
    clip_id: UUID | None = None
    name: str = Field(min_length=1, max_length=200)
    asset_id: UUID
    source_offset_frames: NonNegativeInt = 0
    duration_frames: PositiveInt | None = None
    gain_db: float = Field(default=0.0, ge=-60.0, le=12.0)
    loop: bool = False


class ClipUpdateOperation(APIModel):
    op: Literal["clip.update"]
    op_id: str | None = Field(default=None, min_length=1, max_length=128)
    clip_id: UUID
    name: str | None = Field(default=None, min_length=1, max_length=200)
    asset_id: UUID | None = None
    source_offset_frames: NonNegativeInt | None = None
    duration_frames: PositiveInt | None = None
    clear_duration: bool = False
    gain_db: float | None = Field(default=None, ge=-60.0, le=12.0)
    loop: bool | None = None

    @model_validator(mode="after")
    def require_update(self) -> "ClipUpdateOperation":
        mutable = {
            "name",
            "asset_id",
            "source_offset_frames",
            "duration_frames",
            "gain_db",
            "loop",
        }
        changed = {
            name
            for name in self.model_fields_set & mutable
            if getattr(self, name) is not None
        }
        if not changed and not self.clear_duration:
            raise ValueError("clip.update requires at least one changed field")
        if self.clear_duration and "duration_frames" in self.model_fields_set:
            raise ValueError("clear_duration and duration_frames are mutually exclusive")
        return self


class ClipDuplicateOperation(APIModel):
    op: Literal["clip.duplicate"]
    op_id: str | None = Field(default=None, min_length=1, max_length=128)
    clip_id: UUID
    new_clip_id: UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=200)


class ClipDeleteOperation(APIModel):
    op: Literal["clip.delete"]
    op_id: str | None = Field(default=None, min_length=1, max_length=128)
    clip_id: UUID
    cascade: bool = False


class SlotAssignOperation(APIModel):
    op: Literal["slot.assign"]
    op_id: str | None = Field(default=None, min_length=1, max_length=128)
    slot_id: UUID | None = None
    track_id: UUID
    scene_id: UUID
    clip_id: UUID


class SlotReplaceOperation(APIModel):
    op: Literal["slot.replace"]
    op_id: str | None = Field(default=None, min_length=1, max_length=128)
    track_id: UUID
    scene_id: UUID
    clip_id: UUID


class SlotClearOperation(APIModel):
    op: Literal["slot.clear"]
    op_id: str | None = Field(default=None, min_length=1, max_length=128)
    track_id: UUID
    scene_id: UUID


class TransportUpdateOperation(APIModel):
    op: Literal["transport.update"]
    op_id: str | None = Field(default=None, min_length=1, max_length=128)
    tempo_bpm: float | None = Field(default=None, ge=20.0, le=300.0)
    sample_rate: PositiveInt | None = Field(default=None, le=192000)
    time_signature_numerator: PositiveInt | None = Field(default=None, le=32)
    time_signature_denominator: Literal[1, 2, 4, 8, 16] | None = None
    quantization: Literal["none", "beat", "bar"] | None = None

    @model_validator(mode="after")
    def require_update(self) -> "TransportUpdateOperation":
        fields = self.model_fields_set - {"op", "op_id"}
        if not any(getattr(self, name) is not None for name in fields):
            raise ValueError("transport.update requires at least one changed field")
        return self


class MixerUpdateOperation(APIModel):
    op: Literal["mixer.update"]
    op_id: str | None = Field(default=None, min_length=1, max_length=128)
    track_id: UUID
    gain_db: float | None = Field(default=None, ge=-60.0, le=12.0)
    pan: float | None = Field(default=None, ge=-1.0, le=1.0)
    muted: bool | None = None
    solo: bool | None = None

    @model_validator(mode="after")
    def require_update(self) -> "MixerUpdateOperation":
        fields = self.model_fields_set - {"op", "op_id", "track_id"}
        if not any(getattr(self, name) is not None for name in fields):
            raise ValueError("mixer.update requires at least one changed field")
        return self


ProjectOperation = Annotated[
    SetOperation
    | ProjectRenameOperation
    | TrackCreateOperation
    | TrackRenameOperation
    | TrackReorderOperation
    | TrackDeleteOperation
    | SceneCreateOperation
    | SceneRenameOperation
    | SceneReorderOperation
    | SceneDeleteOperation
    | AssetImportOperation
    | AssetDeleteOperation
    | ClipCreateOperation
    | ClipUpdateOperation
    | ClipDuplicateOperation
    | ClipDeleteOperation
    | SlotAssignOperation
    | SlotReplaceOperation
    | SlotClearOperation
    | TransportUpdateOperation
    | MixerUpdateOperation,
    Field(discriminator="op"),
]


class TransactionRequest(APIModel):
    base_revision: NonNegativeInt
    operations: list[ProjectOperation] = Field(min_length=1, max_length=256)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=128)
    allow_runtime_reset: bool = False


class ApiIssue(APIModel):
    code: str
    path: str = ""
    message: str


class RuntimeImpact(StrEnum):
    NONE = "none"
    INCREMENTAL = "incremental_refresh"
    REBUILD = "transport_preserving_rebuild"
    RESET = "required_reset"


class EntityChanges(APIModel):
    tracks: list[UUID] = Field(default_factory=list)
    scenes: list[UUID] = Field(default_factory=list)
    assets: list[UUID] = Field(default_factory=list)
    clips: list[UUID] = Field(default_factory=list)
    slots: list[UUID] = Field(default_factory=list)


class CascadeImpact(APIModel):
    operation_index: NonNegativeInt
    entity_type: Literal["track", "scene", "asset", "clip"]
    entity_id: UUID
    dependent_ids: EntityChanges = Field(default_factory=EntityChanges)


class TransactionResult(APIModel):
    ok: bool
    committed: bool
    base_revision: NonNegativeInt
    before_revision: NonNegativeInt
    after_revision: NonNegativeInt
    current_revision: NonNegativeInt
    changed_paths: list[str] = Field(default_factory=list)
    created_ids: EntityChanges = Field(default_factory=EntityChanges)
    changed_ids: EntityChanges = Field(default_factory=EntityChanges)
    deleted_ids: EntityChanges = Field(default_factory=EntityChanges)
    cascade_impact: list[CascadeImpact] = Field(default_factory=list)
    runtime_impact: RuntimeImpact = RuntimeImpact.NONE
    runtime_reset_required: bool = False
    runtime_reset_performed: bool = False
    idempotent_replay: bool = False
    warnings: list[ApiIssue] = Field(default_factory=list)
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
    render_position_frame: NonNegativeInt = 0
    audible_position_frame: NonNegativeInt = 0
    queued_latency_frames: NonNegativeInt = 0

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
            render_position_frame=snapshot.engine_snapshot.position_frame,
            audible_position_frame=max(
                0,
                snapshot.engine_snapshot.position_frame
                - getattr(snapshot, "queued_latency_frames", 0),
            ),
            queued_latency_frames=getattr(snapshot, "queued_latency_frames", 0),
        )


class ApplicationSnapshot(APIModel):
    project_id: UUID
    revision: NonNegativeInt
    engine: EngineSnapshotModel
    audio: AudioSnapshotModel


class ReadinessResult(APIModel):
    ok: Literal[True] = True
    status: Literal["ready"] = "ready"
    project_id: UUID
    revision: NonNegativeInt


class ValidationStageResult(APIModel):
    ok: bool
    issues: list[ApiIssue] = Field(default_factory=list)


class LayeredValidationResult(APIModel):
    ok: bool
    stages: dict[str, ValidationStageResult]


TransportOperation = Literal["play", "pause", "stop", "reset"]


class TransportRequest(APIModel):
    operation: TransportOperation


class ClipLaunchRequest(APIModel):
    track_id: UUID
    scene_id: UUID


class ClipStopRequest(APIModel):
    track_id: UUID


class ScheduledActionModel(APIModel):
    target_frame: NonNegativeInt
    affected_track_ids: list[UUID] = Field(default_factory=list)
    changed: bool


class SessionActionResult(APIModel):
    ok: Literal[True] = True
    accepted: bool
    clip_id: UUID | None = None
    action: ScheduledActionModel
    snapshot: ApplicationSnapshot


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
    output_path: str = Field(default="render.wav", min_length=1)
    bars: PositiveInt | None = None
    seconds: PositiveFloat | None = None
    commands: list[RenderCommandRequest] = Field(default_factory=list)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=128)

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


class ExportJobRequest(APIModel):
    output_path: str = Field(default="project.prism", min_length=1)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=128)


class JobPreview(APIModel):
    ok: Literal[True] = True
    kind: Literal["render", "export"]
    project_id: UUID
    revision: NonNegativeInt
    output_path: str
    request: dict[str, Any]


class AudioRestartRequest(APIModel):
    device: int | str | None = None


class ExternalChangeResolutionRequest(APIModel):
    resolution: Literal["detach_source"]


JobState = Literal["queued", "running", "completed", "failed", "cancelled"]
JobKind = Literal["render", "export"]


class BackgroundJob(APIModel):
    job_id: UUID
    kind: JobKind
    state: JobState
    project_id: UUID
    revision: NonNegativeInt
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    request: dict[str, Any]
    output_path: str | None = None
    output_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    created_at: float
    started_at: float | None = None
    finished_at: float | None = None
    error: ApiIssue | None = None


class EventEnvelope(APIModel):
    type: str
    project_id: UUID
    revision: NonNegativeInt
    payload: dict[str, Any] = Field(default_factory=dict)
