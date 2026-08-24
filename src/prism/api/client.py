"""Typed synchronous client for the stable local Prism v1 API."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, BinaryIO, Self, cast
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

import httpx
from websockets.sync.client import ClientConnection, connect
from websockets.typing import Origin

from prism.application.types import (
    ApiIssue,
    ApplicationSnapshot,
    AudioDeviceModel,
    BackgroundJob,
    ClipLaunchRequest,
    ClipStopRequest,
    EventEnvelope,
    ExportJobRequest,
    JobPreview,
    LayeredValidationResult,
    PluginAttachRequest,
    PluginBypassRequest,
    PluginParameterRequest,
    PluginStateCaptureRequest,
    ReadinessResult,
    RenderJobRequest,
    SessionActionResult,
    TransactionRequest,
    TransactionResult,
    TransportRequest,
)
from prism.plugins import (
    PluginCompatibility,
    PluginParameter,
    PluginRegistryDocument,
    PluginTrustRecord,
    PluginWorkerStatus,
)
from prism.project.models import (
    AssetReference,
    AudioClip,
    ClipSlot,
    Project,
    Scene,
    Track,
)


class PrismClientError(Exception):
    """A transport or stable API-envelope failure."""

    def __init__(self, status_code: int, issues: list[ApiIssue]) -> None:
        self.status_code = status_code
        self.issues = issues
        message = "; ".join(issue.message for issue in issues) or "Prism request failed"
        super().__init__(message)


class PrismEventStream:
    """Bounded synchronous iterator over one project's WebSocket events."""

    def __init__(self, base_url: str, project_id: UUID, *, timeout: float) -> None:
        parsed = urlsplit(base_url)
        scheme = "wss" if parsed.scheme == "https" else "ws"
        self._uri = urlunsplit(
            (scheme, parsed.netloc, f"/api/v1/projects/{project_id}/events", "", "")
        )
        self._origin = urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))
        self._timeout = timeout
        self._connection: ClientConnection | None = None

    def __enter__(self) -> Self:
        try:
            self._connection = connect(
                self._uri,
                origin=Origin(self._origin),
                open_timeout=self._timeout,
                close_timeout=self._timeout,
                max_size=1024 * 1024,
                max_queue=16,
                proxy=None,
            )
        except Exception as error:
            raise PrismClientError(
                0,
                [ApiIssue(code="transport_error", message=str(error))],
            ) from error
        return self

    def receive(self, timeout: float | None = None) -> EventEnvelope:
        connection = self._connection
        if connection is None:
            raise RuntimeError("Event stream must be opened as a context manager")
        try:
            message = connection.recv(timeout=timeout)
        except TimeoutError:
            raise
        except Exception as error:
            raise PrismClientError(
                0,
                [ApiIssue(code="event_stream_closed", message=str(error))],
            ) from error
        try:
            if isinstance(message, bytes):
                message = message.decode("utf-8")
            payload = json.loads(message)
            if not isinstance(payload, dict):
                raise ValueError("Event was not a JSON object")
            return EventEnvelope.model_validate(payload)
        except (UnicodeDecodeError, ValueError) as error:
            raise PrismClientError(
                0,
                [ApiIssue(code="invalid_response", message="Event was not valid JSON")],
            ) from error

    def __iter__(self) -> Self:
        return self

    def __next__(self) -> EventEnvelope:
        return self.receive()

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()


class PrismClient:
    """Typed client used by agents and the complete Phase 6 CLI."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8765",
        *,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._client = httpx.Client(
            base_url=self._base_url,
            timeout=timeout,
            transport=transport,
            headers={"Accept": "application/json"},
        )

    def health(self) -> dict[str, Any]:
        return self._json("GET", "/api/v1/health")

    def readiness(self) -> ReadinessResult:
        return ReadinessResult.model_validate(self._json("GET", "/api/v1/readiness"))

    def version(self) -> dict[str, Any]:
        return self._json("GET", "/api/v1/version")

    def capabilities(self) -> dict[str, Any]:
        return self._json("GET", "/api/v1/capabilities")

    def schemas(self) -> dict[str, Any]:
        return self._json("GET", "/api/v1/schemas")

    def get_project(self, project_id: UUID) -> Project:
        payload = self._json("GET", f"/api/v1/projects/{project_id}")
        return Project.model_validate(payload["project"])

    def plugin_config(self) -> dict[str, Any]:
        return cast(dict[str, Any], self._json("GET", "/api/v1/plugins/config")["config"])

    def add_plugin_search_path(self, path: Path | str) -> list[str]:
        payload = self._json(
            "POST", "/api/v1/plugins/search-paths", json={"path": str(path)}
        )
        return [str(item) for item in payload["search_paths"]]

    def remove_plugin_search_path(self, path: Path | str) -> list[str]:
        payload = self._json(
            "DELETE", "/api/v1/plugins/search-paths", json={"path": str(path)}
        )
        return [str(item) for item in payload["search_paths"]]

    def trust_plugin(self, path: Path | str) -> PluginTrustRecord:
        payload = self._json("POST", "/api/v1/plugins/trust", json={"path": str(path)})
        return PluginTrustRecord.model_validate(payload["trust"])

    def revoke_plugin(self, path: Path | str) -> None:
        self._json("DELETE", "/api/v1/plugins/trust", json={"path": str(path)})

    def scan_plugins(self) -> PluginRegistryDocument:
        return PluginRegistryDocument.model_validate(
            self._json("POST", "/api/v1/plugins/scan")
        )

    def list_plugins(self) -> PluginRegistryDocument:
        return PluginRegistryDocument.model_validate(self._json("GET", "/api/v1/plugins"))

    def plugin_worker_status(self) -> PluginWorkerStatus:
        return PluginWorkerStatus.model_validate(
            self._json("GET", "/api/v1/plugins/worker")
        )

    def restart_plugin_worker(self) -> PluginWorkerStatus:
        return PluginWorkerStatus.model_validate(
            self._json("POST", "/api/v1/plugins/worker/restart")
        )

    def plugin_compatibility(self, project_id: UUID) -> list[PluginCompatibility]:
        payload = self._json(
            "GET", f"/api/v1/projects/{project_id}/plugins/compatibility"
        )
        return [PluginCompatibility.model_validate(item) for item in payload["plugins"]]

    def attach_plugin(
        self,
        project_id: UUID,
        track_id: UUID,
        registry_id: UUID,
        request: PluginAttachRequest,
        *,
        preview: bool = False,
    ) -> TransactionResult:
        payload = self._json(
            "POST",
            f"/api/v1/projects/{project_id}/tracks/{track_id}/plugins/{registry_id}",
            params={"preview": preview},
            json=request.model_dump(mode="json", exclude_unset=True),
            allow_error_envelope=True,
        )
        return TransactionResult.model_validate(payload)

    def plugin_parameters(
        self,
        project_id: UUID,
        instance_id: UUID,
    ) -> list[PluginParameter]:
        payload = self._json(
            "GET",
            f"/api/v1/projects/{project_id}/plugins/{instance_id}/parameters",
        )
        return [PluginParameter.model_validate(item) for item in payload["parameters"]]

    def update_plugin_parameter(
        self,
        project_id: UUID,
        instance_id: UUID,
        parameter_id: str,
        request: PluginParameterRequest,
        *,
        preview: bool = False,
    ) -> TransactionResult:
        payload = self._json(
            "POST",
            (
                f"/api/v1/projects/{project_id}/plugins/{instance_id}/parameters/"
                f"{parameter_id}"
            ),
            params={"preview": preview},
            json=request.model_dump(mode="json", exclude_unset=True),
            allow_error_envelope=True,
        )
        return TransactionResult.model_validate(payload)

    def update_plugin_bypass(
        self,
        project_id: UUID,
        instance_id: UUID,
        request: PluginBypassRequest,
        *,
        preview: bool = False,
    ) -> TransactionResult:
        payload = self._json(
            "POST",
            f"/api/v1/projects/{project_id}/plugins/{instance_id}/bypass",
            params={"preview": preview},
            json=request.model_dump(mode="json", exclude_unset=True),
            allow_error_envelope=True,
        )
        return TransactionResult.model_validate(payload)

    def capture_plugin_state(
        self,
        project_id: UUID,
        instance_id: UUID,
        request: PluginStateCaptureRequest,
    ) -> TransactionResult:
        payload = self._json(
            "POST",
            f"/api/v1/projects/{project_id}/plugins/{instance_id}/state",
            json=request.model_dump(mode="json", exclude_unset=True),
            allow_error_envelope=True,
        )
        return TransactionResult.model_validate(payload)

    def get_state(self, project_id: UUID) -> ApplicationSnapshot:
        payload = self._json("GET", f"/api/v1/projects/{project_id}/state")
        return ApplicationSnapshot.model_validate(payload)

    def validate_project(self, project_id: UUID) -> LayeredValidationResult:
        payload = self._json("GET", f"/api/v1/projects/{project_id}/validation")
        return LayeredValidationResult.model_validate(payload)

    def list_tracks(self, project_id: UUID) -> list[Track]:
        payload = self._json("GET", f"/api/v1/projects/{project_id}/tracks")
        return [Track.model_validate(item) for item in payload["tracks"]]

    def list_scenes(self, project_id: UUID) -> list[Scene]:
        payload = self._json("GET", f"/api/v1/projects/{project_id}/scenes")
        return [Scene.model_validate(item) for item in payload["scenes"]]

    def list_clips(self, project_id: UUID) -> list[AudioClip]:
        payload = self._json("GET", f"/api/v1/projects/{project_id}/clips")
        return [AudioClip.model_validate(item) for item in payload["clips"]]

    def list_assets(self, project_id: UUID) -> list[AssetReference]:
        payload = self._json("GET", f"/api/v1/projects/{project_id}/assets")
        return [AssetReference.model_validate(item) for item in payload["assets"]]

    def list_slots(self, project_id: UUID) -> list[ClipSlot]:
        payload = self._json("GET", f"/api/v1/projects/{project_id}/slots")
        return [ClipSlot.model_validate(item) for item in payload["slots"]]

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
        upload_id: UUID | None = None,
    ) -> dict[str, Any]:
        if hasattr(source, "read"):
            stream = source
            upload_name = filename or "upload.wav"
            payload = self._json(
                "POST",
                f"/api/v1/projects/{project_id}/uploads",
                params=None if upload_id is None else {"upload_id": str(upload_id)},
                files={"file": (upload_name, stream, "application/octet-stream")},
            )["upload"]
            return cast(dict[str, Any], payload)
        path = Path(source)
        with path.open("rb") as stream:
            return self.upload_audio(
                project_id,
                stream,
                filename=filename or path.name,
                upload_id=upload_id,
            )

    def discard_upload(self, project_id: UUID, upload_id: UUID) -> None:
        self._json("DELETE", f"/api/v1/projects/{project_id}/uploads/{upload_id}")

    def transport(
        self,
        project_id: UUID,
        request: TransportRequest,
    ) -> ApplicationSnapshot:
        payload = self._json(
            "POST",
            f"/api/v1/projects/{project_id}/transport",
            json=request.model_dump(mode="json"),
        )
        return ApplicationSnapshot.model_validate(payload["snapshot"])

    def launch_slot(
        self,
        project_id: UUID,
        request: ClipLaunchRequest,
    ) -> SessionActionResult:
        payload = self._json(
            "POST",
            f"/api/v1/projects/{project_id}/session/launch",
            json=request.model_dump(mode="json"),
        )
        return SessionActionResult.model_validate(payload)

    def stop_track(
        self,
        project_id: UUID,
        request: ClipStopRequest,
    ) -> SessionActionResult:
        payload = self._json(
            "POST",
            f"/api/v1/projects/{project_id}/session/stop",
            json=request.model_dump(mode="json"),
        )
        return SessionActionResult.model_validate(payload)

    def list_devices(self) -> list[AudioDeviceModel]:
        payload = self._json("GET", "/api/v1/audio/devices")
        return [AudioDeviceModel.model_validate(item) for item in payload["devices"]]

    def restart_audio(self, device: int | str | None = None) -> ApplicationSnapshot:
        payload = self._json("POST", "/api/v1/audio/restart", json={"device": device})
        return ApplicationSnapshot.model_validate(payload["snapshot"])

    def preview_render(self, project_id: UUID, request: RenderJobRequest) -> JobPreview:
        payload = self._json(
            "POST",
            f"/api/v1/projects/{project_id}/render-jobs/preview",
            json=request.model_dump(mode="json"),
        )
        return JobPreview.model_validate(payload)

    def submit_render(self, project_id: UUID, request: RenderJobRequest) -> BackgroundJob:
        payload = self._json(
            "POST",
            f"/api/v1/projects/{project_id}/render-jobs",
            json=request.model_dump(mode="json"),
        )
        return BackgroundJob.model_validate(payload["job"])

    def preview_export(self, project_id: UUID, request: ExportJobRequest) -> JobPreview:
        payload = self._json(
            "POST",
            f"/api/v1/projects/{project_id}/export-jobs/preview",
            json=request.model_dump(mode="json"),
        )
        return JobPreview.model_validate(payload)

    def submit_export(self, project_id: UUID, request: ExportJobRequest) -> BackgroundJob:
        payload = self._json(
            "POST",
            f"/api/v1/projects/{project_id}/export-jobs",
            json=request.model_dump(mode="json"),
        )
        return BackgroundJob.model_validate(payload["job"])

    def list_jobs(self, project_id: UUID) -> list[BackgroundJob]:
        payload = self._json("GET", f"/api/v1/projects/{project_id}/jobs")
        return [BackgroundJob.model_validate(item) for item in payload["jobs"]]

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
                raise TimeoutError(f"Prism job did not finish: {job_id}")
            time.sleep(poll_interval)

    def resolve_external_change(self, project_id: UUID) -> None:
        self._json(
            "POST",
            f"/api/v1/projects/{project_id}/external-change/resolve",
            json={"resolution": "detach_source"},
        )

    def events(self, project_id: UUID) -> PrismEventStream:
        return PrismEventStream(self._base_url, project_id, timeout=self._timeout)

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
            raise PrismClientError(
                0,
                [ApiIssue(code="transport_error", message=str(error))],
            ) from error
        try:
            payload = response.json()
        except ValueError as error:
            raise PrismClientError(
                response.status_code,
                [ApiIssue(code="invalid_response", message="API response was not JSON")],
            ) from error
        if not isinstance(payload, dict):
            raise PrismClientError(
                response.status_code,
                [ApiIssue(code="invalid_response", message="API response was not an object")],
            )
        if response.is_error and not allow_error_envelope:
            issues = [ApiIssue.model_validate(item) for item in payload.get("errors", [])]
            if not issues:
                issues = [
                    ApiIssue(
                        code="http_error",
                        message=f"Prism returned HTTP {response.status_code}",
                    )
                ]
            raise PrismClientError(response.status_code, issues)
        return cast(dict[str, Any], payload)
