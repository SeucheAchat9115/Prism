"""Strict, serializable project models for the first VibeSound schema."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, NonNegativeInt, PositiveInt, field_validator

CURRENT_SCHEMA_VERSION = 1
EntityId = UUID


class StrictModel(BaseModel):
    """Base model that prevents silent schema drift."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


def _clean_name(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("name must not be empty")
    return value


class ProjectRevision(StrictModel):
    number: NonNegativeInt = 0


class MixerState(StrictModel):
    gain_db: float = Field(default=0.0, ge=-60.0, le=12.0)
    pan: float = Field(default=0.0, ge=-1.0, le=1.0)
    muted: bool = False
    solo: bool = False


class TransportState(StrictModel):
    tempo_bpm: float = Field(default=120.0, ge=20.0, le=300.0)
    sample_rate: PositiveInt = Field(default=44100, le=192000)
    time_signature_numerator: PositiveInt = Field(default=4, le=32)
    time_signature_denominator: Literal[1, 2, 4, 8, 16] = 4
    quantization: Literal["none", "beat", "bar"] = "bar"


class Track(StrictModel):
    id: EntityId = Field(default_factory=uuid4)
    name: str = Field(min_length=1, max_length=200)
    order: NonNegativeInt = 0
    mixer: MixerState = Field(default_factory=MixerState)

    _normalize_name = field_validator("name", mode="before")(_clean_name)


class Scene(StrictModel):
    id: EntityId = Field(default_factory=uuid4)
    name: str = Field(min_length=1, max_length=200)
    order: NonNegativeInt = 0

    _normalize_name = field_validator("name", mode="before")(_clean_name)


class AssetReference(StrictModel):
    id: EntityId = Field(default_factory=uuid4)
    kind: Literal["audio"] = "audio"
    member_path: str
    original_name: str = Field(min_length=1, max_length=255)
    size_bytes: NonNegativeInt
    sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    sample_rate: PositiveInt
    channels: PositiveInt
    frames: NonNegativeInt
    format: str = Field(min_length=1, max_length=64)

    @field_validator("member_path")
    @classmethod
    def validate_member_path(cls, value: str) -> str:
        path = PurePosixPath(value)
        if (
            not value
            or "\\" in value
            or path.is_absolute()
            or ".." in path.parts
            or not value.startswith("assets/audio/")
        ):
            raise ValueError("member_path must be a safe relative assets/audio path")
        return value

    _normalize_name = field_validator("original_name", mode="before")(_clean_name)


class AudioClip(StrictModel):
    id: EntityId = Field(default_factory=uuid4)
    name: str = Field(min_length=1, max_length=200)
    asset_id: EntityId
    source_offset_frames: NonNegativeInt = 0
    duration_frames: PositiveInt | None = None
    gain_db: float = Field(default=0.0, ge=-60.0, le=12.0)
    loop: bool = False

    _normalize_name = field_validator("name", mode="before")(_clean_name)


class ClipSlot(StrictModel):
    id: EntityId = Field(default_factory=uuid4)
    track_id: EntityId
    scene_id: EntityId
    clip_id: EntityId | None = None


class Project(StrictModel):
    schema_version: Literal[CURRENT_SCHEMA_VERSION] = CURRENT_SCHEMA_VERSION
    project_id: EntityId = Field(default_factory=uuid4)
    name: str = Field(min_length=1, max_length=200)
    revision: ProjectRevision = Field(default_factory=ProjectRevision)
    transport: TransportState = Field(default_factory=TransportState)
    tracks: list[Track] = Field(default_factory=list)
    scenes: list[Scene] = Field(default_factory=list)
    clips: list[AudioClip] = Field(default_factory=list)
    clip_slots: list[ClipSlot] = Field(default_factory=list)
    assets: list[AssetReference] = Field(default_factory=list)

    _normalize_name = field_validator("name", mode="before")(_clean_name)


def new_project(name: str, *, tempo_bpm: float = 120.0, sample_rate: int = 44100) -> Project:
    """Create a valid empty project with the requested transport settings."""

    return Project(
        name=name,
        transport=TransportState(tempo_bpm=tempo_bpm, sample_rate=sample_rate),
    )
