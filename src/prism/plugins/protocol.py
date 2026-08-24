"""Versioned JSON-lines messages for the isolated plugin worker."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

PROTOCOL_VERSION: Literal[1] = 1


class WorkerMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")


class WorkerRequest(WorkerMessage):
    protocol_version: Literal[1] = PROTOCOL_VERSION
    request_id: str = Field(min_length=1, max_length=128)
    method: str = Field(min_length=1, max_length=100)
    params: dict[str, Any] = Field(default_factory=dict)


class WorkerFailure(WorkerMessage):
    code: str
    message: str


class WorkerResponse(WorkerMessage):
    protocol_version: Literal[1] = PROTOCOL_VERSION
    request_id: str
    ok: bool
    result: dict[str, Any] | None = None
    error: WorkerFailure | None = None
