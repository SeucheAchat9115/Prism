"""FastAPI routes for the Phase 5 application service."""

from __future__ import annotations

import asyncio
from queue import Empty
from typing import Any
from uuid import UUID

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from vibesound.application import ApplicationService
from vibesound.application.errors import ApplicationError, EventStreamOverflowError
from vibesound.application.types import (
    ClipLaunchRequest,
    ClipStopRequest,
    RenderJobRequest,
    TransactionRequest,
    TransactionResult,
    TransportRequest,
)
from vibesound.engine.types import ScheduledAction
from vibesound.rendering.types import RenderMetadata


def create_app(service: ApplicationService) -> FastAPI:
    """Create a loopback-ready API app bound to one application service."""

    app = FastAPI(
        title="VibeSound API",
        version="1",
        description="Local versioned control API for one VibeSound project.",
    )
    app.state.vibesound_service = service

    @app.exception_handler(ApplicationError)
    async def application_error_handler(_, error: ApplicationError) -> JSONResponse:
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
    async def request_validation_handler(_, error: RequestValidationError) -> JSONResponse:
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

    @app.get("/api/v1/projects/{project_id}")
    async def get_project(project_id: UUID) -> dict[str, object]:
        current = require_project(project_id).get_project()
        return {"project": current.model_dump(mode="json")}

    @app.get("/api/v1/projects/{project_id}/state")
    async def get_state(project_id: UUID) -> dict[str, object]:
        snapshot = require_project(project_id).get_snapshot()
        return snapshot.model_dump(mode="json")

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
            "action": _action_json(action),
            "snapshot": current.get_snapshot().model_dump(mode="json"),
        }

    @app.post("/api/v1/projects/{project_id}/render")
    async def render(project_id: UUID, request: RenderJobRequest) -> dict[str, object]:
        metadata = require_project(project_id).render(request)
        return {"ok": True, "metadata": _metadata_json(metadata)}

    @app.websocket("/api/v1/projects/{project_id}/events")
    async def events(websocket: WebSocket, project_id: UUID) -> None:
        try:
            current = require_project(project_id)
        except ApplicationError:
            await websocket.close(code=1008)
            return
        await websocket.accept()
        subscription = current.subscribe()
        try:
            while True:
                try:
                    event = await asyncio.to_thread(subscription.get, 0.5)
                except Empty:
                    continue
                await websocket.send_json(event.model_dump(mode="json"))
        except WebSocketDisconnect:
            pass
        except EventStreamOverflowError:
            await websocket.close(code=1013)
        finally:
            subscription.close()

    return app


def _transaction_response(result: TransactionResult) -> JSONResponse:
    status_code = 200
    if not result.ok:
        codes = {issue.code for issue in result.errors}
        if "stale_revision" in codes:
            status_code = 409
        elif "persistence_error" in codes or "audio_backend_invalid" in codes:
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
