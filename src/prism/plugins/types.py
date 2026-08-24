"""Strict machine-local contracts for VST3 discovery and worker control."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, NonNegativeInt, PositiveFloat

Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class PluginModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PluginTrustRecord(PluginModel):
    """A user's approval for the exact bytes at one VST3 path."""

    path: str = Field(min_length=1)
    binary_sha256: Sha256
    trusted_at: float
    enabled: bool = True


class PluginConfig(PluginModel):
    """Machine-local plugin policy; never embedded in portable projects."""

    schema_version: Literal[1] = 1
    search_paths: list[str] = Field(default_factory=list)
    trust: list[PluginTrustRecord] = Field(default_factory=list)
    discovery_timeout_seconds: PositiveFloat = 15.0
    process_timeout_seconds: PositiveFloat = 10.0
    max_state_bytes: NonNegativeInt = 16 * 1024 * 1024


class PluginParameter(PluginModel):
    """A normalized automatable control exposed by a loaded plugin."""

    id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=200)
    raw_value: float = Field(ge=0.0, le=1.0)
    value: str = ""


class PluginRecord(PluginModel):
    """One candidate or successfully probed VST3 entry in the local registry."""

    registry_id: UUID
    path: str = Field(min_length=1)
    plugin_identifier: str = Field(min_length=1, max_length=500)
    binary_sha256: Sha256
    name: str = Field(min_length=1, max_length=200)
    manufacturer: str = Field(default="Unknown", min_length=1, max_length=200)
    version: str = Field(default="Unknown", min_length=1, max_length=100)
    category: str = Field(default="Effect", min_length=1, max_length=100)
    trusted: bool = False
    available: bool = False
    error: str | None = None


class PluginRegistryDocument(PluginModel):
    schema_version: Literal[1] = 1
    scanned_at: float
    plugins: list[PluginRecord] = Field(default_factory=list)


class PluginWorkerStatus(PluginModel):
    protocol_version: Literal[1] = 1
    state: Literal["stopped", "ready", "failed"]
    pid: int | None = None
    restart_count: NonNegativeInt = 0
    last_error: str | None = None


class PluginCompatibility(PluginModel):
    instance_id: UUID
    registry_id: UUID
    status: Literal["ready", "missing", "untrusted", "changed", "failed", "bypassed"]
    message: str
