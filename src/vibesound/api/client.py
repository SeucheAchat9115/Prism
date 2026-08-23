"""Typed synchronous client for the stable local VibeSound v1 API."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, BinaryIO, Self, cast
from uuid import UUID

import httpx

from vibesound.application.types import (
    ApiIssue,
    BackgroundJob,
    ExportJobRequest,
    RenderJobRequest,
    TransactionRequest,
    TransactionResult,
)
from vibesound.project.models import Project


class VibeSoundClientError(Exception):
    """A transport or stable API-envelope failure."""

    def __init__(self, status_code: int, issues: list[ApiIssue]) -> None:
        self.status_code = status_code
        self.issues = issues
        message = "; ".join(issue.message for issue in issues) or "VibeSound request failed"
        super().__init__(message)


class VibeSoundClient:
    """Small typed client used by agents, the demo launcher, and Phase 6."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8765",
        *,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            transport=transport,
            headers={"Accept": "application/json"},
        )

    def health(self) -> dict[str, Any]:
        return self._json("GET", "/api/v1/health")

    def readiness(self) -> dict[str, Any]:
        return self._json("GET", "/api/v1/readiness")

    def capabilities(self) -> dict[str, Any]:
        return self._json("GET", "/api/v1/capabilities")

    def schemas(self) -> dict[str, Any]:
        return self._json("GET", "/api/v1/schemas")

    def get_project(self, project_id: UUID) -> Project:
        payload = self._json("GET", f"/api/v1/projects/{project_id}")
        return Project.model_validate(payload["project"])

    def resolve_name(self, project_id: UUID, entity_type: str, name: str) -> UUID:
        payload = self._json(
            "GET",
            f"/api/v1/projects/{project_id}/resolve",
            params={"entity_type": entity_type, "name": name},
        )
        return UUID(payload["id"])

    def preview_transaction(
        self,
        project_id: UUID,
        request: TransactionRequest,
    ) -> TransactionResult:
        payload = self._json(
            "POST",
            f"/api/v1/projects/{project_id}/transactions/preview",
            json=request.model_dump(mode="json", exclude_unset=True),
            allow_error_envelope=True,
        )
        return TransactionResult.model_validate(payload)

    def commit_transaction(
        self,
        project_id: UUID,
        request: TransactionRequest,
    ) -> TransactionResult:
        payload = self._json(
            "POST",
            f"/api/v1/projects/{project_id}/transactions",
            json=request.model_dump(mode="json", exclude_unset=True),
            allow_error_envelope=True,
        )
        return TransactionResult.model_validate(payload)

    def upload_audio(
        self,
        project_id: UUID,
        source: Path | str | BinaryIO,
        *,
        filename: str | None = None,
    ) -> dict[str, Any]:
        if hasattr(source, "read"):
            stream = source
            upload_name = filename or "upload.wav"
            payload = self._json(
                "POST",
                f"/api/v1/projects/{project_id}/uploads",
                files={"file": (upload_name, stream, "application/octet-stream")},
            )["upload"]
            return cast(dict[str, Any], payload)
        path = Path(source)
        with path.open("rb") as stream:
            return self.upload_audio(project_id, stream, filename=filename or path.name)

    def submit_render(self, project_id: UUID, request: RenderJobRequest) -> BackgroundJob:
        payload = self._json(
            "POST",
            f"/api/v1/projects/{project_id}/render-jobs",
            json=request.model_dump(mode="json"),
        )
        return BackgroundJob.model_validate(payload["job"])

    def submit_export(self, project_id: UUID, request: ExportJobRequest) -> BackgroundJob:
        payload = self._json(
            "POST",
            f"/api/v1/projects/{project_id}/export-jobs",
            json=request.model_dump(mode="json"),
        )
        return BackgroundJob.model_validate(payload["job"])

    def get_job(self, project_id: UUID, job_id: UUID) -> BackgroundJob:
        payload = self._json("GET", f"/api/v1/projects/{project_id}/jobs/{job_id}")
        return BackgroundJob.model_validate(payload["job"])

    def cancel_job(self, project_id: UUID, job_id: UUID) -> BackgroundJob:
        payload = self._json("DELETE", f"/api/v1/projects/{project_id}/jobs/{job_id}")
        return BackgroundJob.model_validate(payload["job"])

    def wait_for_job(
        self,
        project_id: UUID,
        job_id: UUID,
        *,
        timeout: float = 300.0,
        poll_interval: float = 0.05,
    ) -> BackgroundJob:
        deadline = time.monotonic() + timeout
        while True:
            job = self.get_job(project_id, job_id)
            if job.state in {"completed", "failed", "cancelled"}:
                return job
            if time.monotonic() >= deadline:
                raise TimeoutError(f"VibeSound job did not finish: {job_id}")
            time.sleep(poll_interval)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()

    def _json(
        self,
        method: str,
        path: str,
        *,
        allow_error_envelope: bool = False,
        **kwargs: Any,
    ) -> dict[str, Any]:
        try:
            response = self._client.request(method, path, **kwargs)
        except httpx.HTTPError as error:
            raise VibeSoundClientError(
                0,
                [ApiIssue(code="transport_error", message=str(error))],
            ) from error
        try:
            payload = response.json()
        except ValueError as error:
            raise VibeSoundClientError(
                response.status_code,
                [ApiIssue(code="invalid_response", message="API response was not JSON")],
            ) from error
        if not isinstance(payload, dict):
            raise VibeSoundClientError(
                response.status_code,
                [ApiIssue(code="invalid_response", message="API response was not an object")],
            )
        if response.is_error and not allow_error_envelope:
            issues = [ApiIssue.model_validate(item) for item in payload.get("errors", [])]
            raise VibeSoundClientError(response.status_code, issues)
        return cast(dict[str, Any], payload)
