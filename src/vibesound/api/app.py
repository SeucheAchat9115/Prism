"""Hardened loopback FastAPI surface for the Phase 5.5 application service."""

from __future__ import annotations

import asyncio
from pathlib import Path
from queue import Empty
from typing import Any, Literal
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import FastAPI, File, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.base import RequestResponseEndpoint
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import Response
from starlette.staticfiles import StaticFiles
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from vibesound import __version__
from vibesound.application import ApplicationService
from vibesound.application.errors import ApplicationError, EventStreamOverflowError
from vibesound.application.types import (
    AudioRestartRequest,
    BackgroundJob,
    ClipLaunchRequest,
    ClipStopRequest,
    ExportJobRequest,
    ExternalChangeResolutionRequest,
    RenderJobRequest,
    ScheduledActionModel,
    SessionActionResult,
    TransactionRequest,
    TransactionResult,
    TransportRequest,
)
from vibesound.engine.types import ScheduledAction
from vibesound.rendering.types import RenderMetadata

_MAX_JSON_BODY_BYTES = 16 * 1024 * 1024
_API_VERSION = "v1"
_WEB_ROOT = Path(__file__).resolve().parents[1] / "web"
_UI_SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; connect-src 'self' ws:; object-src 'none'; "
        "base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
    ),
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
}


class _BodyLimitExceeded(Exception):
    pass


class _RequestBodyLimitMiddleware:
    """Count received bytes so chunked bodies cannot bypass Content-Length policy."""

    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        self._app = app
        self._max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or str(scope.get("path", "")).endswith("/uploads"):
            await self._app(scope, receive, send)
            return
        headers = dict(scope.get("headers", ()))
        raw_length = headers.get(b"content-length")
        if raw_length is not None:
            try:
                declared = int(raw_length)
            except ValueError:
                await _error_response(
                    400,
                    "invalid_content_length",
                    "Content-Length must be an integer",
                )(scope, receive, send)
                return
            if declared > self._max_bytes:
                await _error_response(
                    413,
                    "request_too_large",
                    "Request body exceeds the configured limit",
                )(scope, receive, send)
                return
        consumed = 0

        async def limited_receive() -> Message:
            nonlocal consumed
            message = await receive()
            if message["type"] == "http.request":
                consumed += len(message.get("body", b""))
                if consumed > self._max_bytes:
                    raise _BodyLimitExceeded
            return message

        try:
            await self._app(scope, limited_receive, send)
        except _BodyLimitExceeded:
            await _error_response(
                413,
                "request_too_large",
                "Request body exceeds the configured limit",
            )(scope, receive, send)


def create_app(service: ApplicationService) -> FastAPI:
    """Create a host/origin-restricted API bound to one application service."""

    app = FastAPI(
        title="VibeSound API",
        version=__version__,
        description="Local versioned control API for one VibeSound project.",
    )
    app.state.vibesound_service = service
    app.add_middleware(_RequestBodyLimitMiddleware, max_bytes=_MAX_JSON_BODY_BYTES)
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["127.0.0.1", "localhost", "[::1]", "testserver"],
    )

    @app.middleware("http")
    async def enforce_local_request_policy(
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        host = request.headers.get("host", "")
        if not _is_allowed_host(host):
            return _error_response(400, "host_rejected", "Request host is not allowed")
        origin = request.headers.get("origin")
        if origin is not None and not _same_origin(origin, host):
            return _error_response(403, "origin_rejected", "Request origin is not allowed")
        response = await call_next(request)
        if request.url.path == "/" or request.url.path.startswith("/assets/"):
            response.headers.update(_UI_SECURITY_HEADERS)
        return response

    @app.exception_handler(ApplicationError)
    async def application_error_handler(
        _request: Request,
        error: ApplicationError,
    ) -> JSONResponse:
        payload: dict[str, Any] = {
            "ok": False,
            "errors": [
                {
                    "code": error.code,
                    "path": error.path,
                    "message": error.message,
                }
            ],
        }
        if error.current_revision is not None:
            payload["current_revision"] = error.current_revision
        return JSONResponse(status_code=error.status_code, content=payload)

    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(
        _request: Request,
        error: RequestValidationError,
    ) -> JSONResponse:
        issues = []
        for item in error.errors():
            location = [str(part) for part in item.get("loc", ()) if part != "body"]
            issues.append(
                {
                    "code": "invalid_request",
                    "path": "/" + "/".join(location),
                    "message": str(item.get("msg", "Invalid request")),
                }
            )
        return JSONResponse(status_code=422, content={"ok": False, "errors": issues})

    def require_project(project_id: UUID) -> ApplicationService:
        if service.project_id != project_id:
            raise ApplicationError(
                "Project does not belong to this service",
                code="project_not_found",
                status_code=404,
            )
        return service

    @app.get("/health")
    @app.get("/api/v1/health")
    async def health() -> dict[str, object]:
        return {"ok": True, "status": "healthy"}

    @app.get("/ready")
    @app.get("/api/v1/readiness")
    async def readiness() -> dict[str, object]:
        snapshot = service.get_snapshot()
        return {
            "ok": True,
            "status": "ready",
            "project_id": str(snapshot.project_id),
            "revision": snapshot.revision,
        }

    @app.get("/api/v1/version")
    async def version() -> dict[str, object]:
        return {"application_version": __version__, "api_version": _API_VERSION}

    @app.get("/", include_in_schema=False)
    async def browser_session() -> FileResponse:
        return FileResponse(_WEB_ROOT / "index.html", media_type="text/html")

    @app.get("/api/v1/capabilities")
    async def capabilities() -> dict[str, object]:
        return {
            "api_version": _API_VERSION,
            "storage": {
                "working_project": True,
                "portable_archive_export": True,
                "source_archives_are_immutable": True,
            },
            "authoring": {
                "typed_operations": True,
                "preview": True,
                "cascade_preview": True,
                "idempotency": True,
                "max_operations": 256,
            },
            "runtime": {
                "device_free": True,
                "runtime_impact": True,
                "explicit_reset": True,
                "soxr_quality": "HQ",
            },
            "jobs": {"render": True, "export": True, "cancellation": True},
            "ui": {"browser_session": True, "path": "/"},
        }

    @app.get("/api/v1/schemas")
    async def schemas() -> dict[str, object]:
        return {
            "transaction_request": TransactionRequest.model_json_schema(),
            "render_job_request": RenderJobRequest.model_json_schema(),
            "export_job_request": ExportJobRequest.model_json_schema(),
        }

    @app.get("/api/v1/projects/{project_id}")
    async def get_project(project_id: UUID) -> dict[str, object]:
        current = require_project(project_id).get_project()
        return {"project": current.model_dump(mode="json")}

    @app.get("/api/v1/projects/{project_id}/state")
    async def get_state(project_id: UUID) -> dict[str, object]:
        snapshot = require_project(project_id).get_snapshot()
        return snapshot.model_dump(mode="json")

    @app.get("/api/v1/projects/{project_id}/validation")
    async def validate_project(project_id: UUID) -> dict[str, object]:
        return require_project(project_id).validate().as_dict()

    @app.get("/api/v1/projects/{project_id}/tracks")
    async def get_tracks(project_id: UUID) -> dict[str, object]:
        return {
            "tracks": [
                item.model_dump(mode="json")
                for item in require_project(project_id).get_project().tracks
            ]
        }

    @app.get("/api/v1/projects/{project_id}/scenes")
    async def get_scenes(project_id: UUID) -> dict[str, object]:
        return {
            "scenes": [
                item.model_dump(mode="json")
                for item in require_project(project_id).get_project().scenes
            ]
        }

    @app.get("/api/v1/projects/{project_id}/clips")
    async def get_clips(project_id: UUID) -> dict[str, object]:
        return {
            "clips": [
                item.model_dump(mode="json")
                for item in require_project(project_id).get_project().clips
            ]
        }

    @app.get("/api/v1/projects/{project_id}/assets")
    async def get_assets(project_id: UUID) -> dict[str, object]:
        return {
            "assets": [
                item.model_dump(mode="json")
                for item in require_project(project_id).get_project().assets
            ]
        }

    @app.get("/api/v1/projects/{project_id}/slots")
    async def get_slots(project_id: UUID) -> dict[str, object]:
        return {
            "slots": [
                item.model_dump(mode="json")
                for item in require_project(project_id).get_project().clip_slots
            ]
        }

    @app.get("/api/v1/projects/{project_id}/resolve")
    async def resolve_name(
        project_id: UUID,
        entity_type: Literal["track", "scene", "clip", "asset"],
        name: str,
    ) -> dict[str, object]:
        entity_id = require_project(project_id).resolve_name(entity_type, name)
        return {"entity_type": entity_type, "name": name, "id": str(entity_id)}

    @app.post("/api/v1/projects/{project_id}/uploads", status_code=201)
    async def upload_audio(
        project_id: UUID,
        file: UploadFile = File(...),
        upload_id: UUID | None = None,
    ) -> dict[str, object]:
        upload = require_project(project_id).stage_audio(
            file.file,
            file.filename or "upload.wav",
            upload_id=upload_id,
        )
        return {"ok": True, "upload": upload.to_public_dict()}

    @app.delete("/api/v1/projects/{project_id}/uploads/{upload_id}")
    async def discard_upload(project_id: UUID, upload_id: UUID) -> dict[str, object]:
        require_project(project_id).discard_upload(upload_id)
        return {"ok": True, "upload_id": str(upload_id), "discarded": True}

    @app.post("/api/v1/projects/{project_id}/transactions/preview")
    async def preview_transaction(
        project_id: UUID,
        request: TransactionRequest,
    ) -> JSONResponse:
        result = require_project(project_id).preview_transaction(request)
        return _transaction_response(result)

    @app.post("/api/v1/projects/{project_id}/transactions")
    async def commit_transaction(
        project_id: UUID,
        request: TransactionRequest,
    ) -> JSONResponse:
        result = require_project(project_id).commit_transaction(request)
        return _transaction_response(result)

    @app.post("/api/v1/projects/{project_id}/external-change/resolve")
    async def resolve_external_change(
        project_id: UUID,
        request: ExternalChangeResolutionRequest,
    ) -> dict[str, object]:
        require_project(project_id).resolve_external_change(request.resolution)
        return {"ok": True, "resolution": request.resolution}

    @app.post("/api/v1/projects/{project_id}/transport")
    async def transport(project_id: UUID, request: TransportRequest) -> dict[str, object]:
        snapshot = require_project(project_id).transport(request)
        return {"ok": True, "snapshot": snapshot.model_dump(mode="json")}

    @app.post("/api/v1/projects/{project_id}/clips/{clip_id}/launch")
    async def launch_clip(
        project_id: UUID,
        clip_id: UUID,
        request: ClipLaunchRequest,
    ) -> dict[str, object]:
        current = require_project(project_id)
        action = current.launch_clip(clip_id, request)
        return {
            "ok": True,
            "accepted": action.changed,
            "action": _action_json(action),
            "snapshot": current.get_snapshot().model_dump(mode="json"),
        }

    @app.post("/api/v1/projects/{project_id}/clips/{clip_id}/stop")
    async def stop_clip(
        project_id: UUID,
        clip_id: UUID,
        request: ClipStopRequest,
    ) -> dict[str, object]:
        current = require_project(project_id)
        action = current.stop_clip(clip_id, request)
        return {
            "ok": True,
            "accepted": action.changed,
            "action": _action_json(action),
            "snapshot": current.get_snapshot().model_dump(mode="json"),
        }

    @app.post("/api/v1/projects/{project_id}/session/launch")
    async def launch_slot(
        project_id: UUID,
        request: ClipLaunchRequest,
    ) -> dict[str, object]:
        current = require_project(project_id)
        clip_id, action = current.launch_slot(request)
        return SessionActionResult(
            accepted=action.changed,
            clip_id=clip_id,
            action=ScheduledActionModel(
                target_frame=action.target_frame,
                affected_track_ids=list(action.affected_track_ids),
                changed=action.changed,
            ),
            snapshot=current.get_snapshot(),
        ).model_dump(mode="json")

    @app.post("/api/v1/projects/{project_id}/session/stop")
    async def stop_track(
        project_id: UUID,
        request: ClipStopRequest,
    ) -> dict[str, object]:
        current = require_project(project_id)
        clip_id, action = current.stop_track(request)
        return SessionActionResult(
            accepted=action.changed,
            clip_id=clip_id,
            action=ScheduledActionModel(
                target_frame=action.target_frame,
                affected_track_ids=list(action.affected_track_ids),
                changed=action.changed,
            ),
            snapshot=current.get_snapshot(),
        ).model_dump(mode="json")

    @app.get("/api/v1/audio/devices")
    async def devices() -> dict[str, object]:
        return {"devices": [item.model_dump(mode="json") for item in service.list_devices()]}

    @app.post("/api/v1/audio/restart")
    async def restart_audio(request: AudioRestartRequest) -> dict[str, object]:
        snapshot = service.restart_audio(request.device)
        return {"ok": True, "snapshot": snapshot.model_dump(mode="json")}

    @app.post("/api/v1/projects/{project_id}/render-jobs", status_code=202)
    async def submit_render_job(
        project_id: UUID,
        request: RenderJobRequest,
    ) -> dict[str, object]:
        job = require_project(project_id).submit_render(request)
        return {"ok": True, "job": _job_json(job)}

    @app.post("/api/v1/projects/{project_id}/render-jobs/preview")
    async def preview_render_job(
        project_id: UUID,
        request: RenderJobRequest,
    ) -> dict[str, object]:
        return require_project(project_id).preview_render(request).model_dump(mode="json")

    @app.post("/api/v1/projects/{project_id}/export-jobs", status_code=202)
    async def submit_export_job(
        project_id: UUID,
        request: ExportJobRequest,
    ) -> dict[str, object]:
        job = require_project(project_id).submit_export(request)
        return {"ok": True, "job": _job_json(job)}

    @app.post("/api/v1/projects/{project_id}/export-jobs/preview")
    async def preview_export_job(
        project_id: UUID,
        request: ExportJobRequest,
    ) -> dict[str, object]:
        return require_project(project_id).preview_export(request).model_dump(mode="json")

    @app.get("/api/v1/projects/{project_id}/jobs")
    async def list_jobs(project_id: UUID) -> dict[str, object]:
        jobs = require_project(project_id).list_jobs()
        return {"jobs": [_job_json(job) for job in jobs]}

    @app.get("/api/v1/projects/{project_id}/jobs/{job_id}")
    async def get_job(project_id: UUID, job_id: UUID) -> dict[str, object]:
        job = require_project(project_id).get_job(job_id)
        return {"job": _job_json(job)}

    @app.delete("/api/v1/projects/{project_id}/jobs/{job_id}")
    async def cancel_job(project_id: UUID, job_id: UUID) -> dict[str, object]:
        job = require_project(project_id).cancel_job(job_id)
        return {"ok": True, "job": _job_json(job)}

    @app.post("/api/v1/projects/{project_id}/render")
    async def render(project_id: UUID, request: RenderJobRequest) -> dict[str, object]:
        metadata = require_project(project_id).render(request)
        return {"ok": True, "metadata": _metadata_json(metadata)}

    @app.websocket("/api/v1/projects/{project_id}/events")
    async def events(websocket: WebSocket, project_id: UUID) -> None:
        origin = websocket.headers.get("origin")
        if origin is not None and not _same_origin(origin, websocket.headers.get("host", "")):
            await websocket.close(code=1008)
            return
        try:
            current = require_project(project_id)
            subscription = current.subscribe()
        except ApplicationError:
            await websocket.close(code=1008)
            return
        await websocket.accept()
        try:
            while True:
                try:
                    event = await asyncio.to_thread(subscription.get, 0.5)
                except Empty:
                    continue
                except RuntimeError as error:
                    if str(error) == "cannot schedule new futures after shutdown":
                        break
                    raise
                await websocket.send_json(event.model_dump(mode="json"))
        except WebSocketDisconnect:
            pass
        except EventStreamOverflowError:
            try:
                await websocket.close(code=1013)
            except WebSocketDisconnect:
                pass
        finally:
            subscription.close()

    app.mount("/assets", StaticFiles(directory=_WEB_ROOT / "assets"), name="web-assets")
    return app


def _transaction_response(result: TransactionResult) -> JSONResponse:
    status_code = 200
    if not result.ok:
        codes = {issue.code for issue in result.errors}
        if codes.intersection(
            {
                "stale_revision",
                "cascade_required",
                "idempotency_conflict",
                "runtime_reset_required",
                "external_project_change",
            }
        ):
            status_code = 409
        elif codes.intersection({"persistence_error", "audio_backend_invalid"}):
            status_code = 500
        else:
            status_code = 422
    return JSONResponse(status_code=status_code, content=result.model_dump(mode="json"))


def _action_json(action: ScheduledAction) -> dict[str, object]:
    return {
        "target_frame": action.target_frame,
        "affected_track_ids": [str(track_id) for track_id in action.affected_track_ids],
        "changed": action.changed,
    }


def _metadata_json(metadata: RenderMetadata) -> dict[str, object]:
    return {
        "project_id": str(metadata.project_id),
        "revision": metadata.revision,
        "output_path": str(metadata.output_path),
        "format": metadata.format,
        "subtype": metadata.subtype,
        "sample_rate": metadata.sample_rate,
        "channels": metadata.channels,
        "frames": metadata.frames,
        "duration_seconds": metadata.duration_seconds,
    }


def _job_json(job: BackgroundJob) -> dict[str, object]:
    return job.model_dump(mode="json")


def _same_origin(origin: str, host: str) -> bool:
    try:
        parsed = urlsplit(origin)
    except ValueError:
        return False
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    return parsed.netloc.casefold() == host.casefold()


def _is_allowed_host(host: str) -> bool:
    try:
        parsed = urlsplit(f"//{host}")
    except ValueError:
        return False
    return parsed.hostname in {"127.0.0.1", "::1", "localhost", "testserver"}


def _error_response(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={
            "ok": False,
            "errors": [{"code": code, "path": "", "message": message}],
        },
    )
