from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from vibesound.api import VibeSoundClient, VibeSoundClientError
from vibesound.application import ExportJobRequest, RenderJobRequest, TransactionRequest
from vibesound.application.types import BackgroundJob, TransactionResult
from vibesound.project.models import new_project


def test_typed_client_covers_discovery_authoring_upload_and_jobs(tmp_path: Path) -> None:
    project = new_project("Client")
    job_id = uuid4()
    job_polls = 0

    def job(state: str = "completed") -> dict[str, object]:
        return BackgroundJob(
            job_id=job_id,
            kind="render",
            state=state,
            project_id=project.project_id,
            revision=0,
            progress=1.0 if state == "completed" else 0.5,
            request={"seconds": 1.0},
            output_path="render.wav",
            created_at=1.0,
        ).model_dump(mode="json")

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal job_polls
        path = request.url.path
        if path.endswith("/health"):
            return httpx.Response(200, json={"ok": True, "status": "healthy"})
        if path.endswith("/readiness"):
            return httpx.Response(200, json={"ok": True, "status": "ready"})
        if path.endswith("/capabilities") or path.endswith("/schemas"):
            return httpx.Response(200, json={"ok": True})
        if path.endswith("/resolve"):
            return httpx.Response(200, json={"id": str(project.project_id)})
        if path.endswith("/uploads"):
            return httpx.Response(201, json={"upload": {"upload_id": str(uuid4())}})
        if path.endswith("/transactions") or path.endswith("/transactions/preview"):
            return httpx.Response(
                200,
                json=TransactionResult(
                    ok=True,
                    committed=not path.endswith("preview"),
                    base_revision=0,
                    before_revision=0,
                    after_revision=1,
                    current_revision=1,
                ).model_dump(mode="json"),
            )
        if path.endswith("/render-jobs") or path.endswith("/export-jobs"):
            return httpx.Response(202, json={"job": job()})
        if path.endswith(f"/jobs/{job_id}"):
            if request.method == "DELETE":
                return httpx.Response(200, json={"job": job("cancelled")})
            job_polls += 1
            state = "queued" if job_polls == 1 else "completed"
            return httpx.Response(200, json={"job": job(state)})
        return httpx.Response(200, json={"project": project.model_dump(mode="json")})

    audio = tmp_path / "upload.wav"
    audio.write_bytes(b"RIFF-test")
    transport = httpx.MockTransport(handler)
    with VibeSoundClient("http://testserver", transport=transport) as client:
        assert client.health()["status"] == "healthy"
        assert client.readiness()["status"] == "ready"
        assert client.capabilities()["ok"]
        assert client.schemas()["ok"]
        assert client.get_project(project.project_id).name == "Client"
        assert client.resolve_name(project.project_id, "track", "name") == project.project_id

        transaction = TransactionRequest(
            base_revision=0,
            operations=[{"op": "project.rename", "name": "Renamed"}],
        )
        assert client.preview_transaction(project.project_id, transaction).ok
        assert client.commit_transaction(project.project_id, transaction).committed
        assert "upload_id" in client.upload_audio(project.project_id, audio)

        rendered = client.submit_render(
            project.project_id,
            RenderJobRequest(seconds=1.0),
        )
        exported = client.submit_export(project.project_id, ExportJobRequest())
        assert rendered.job_id == exported.job_id == job_id
        assert client.wait_for_job(project.project_id, job_id).state == "completed"
        assert client.cancel_job(project.project_id, job_id).state == "cancelled"


def test_typed_client_normalizes_error_envelopes_and_invalid_json() -> None:
    responses = iter(
        [
            httpx.Response(
                409,
                json={
                    "ok": False,
                    "errors": [{"code": "conflict", "path": "", "message": "Conflict"}],
                },
            ),
            httpx.Response(500, content=b"not-json"),
            httpx.Response(500, content=json.dumps([]).encode()),
        ]
    )
    client = VibeSoundClient(
        "http://testserver",
        transport=httpx.MockTransport(lambda _request: next(responses)),
    )
    try:
        with pytest.raises(VibeSoundClientError) as conflict:
            client.health()
        assert conflict.value.status_code == 409
        assert conflict.value.issues[0].code == "conflict"
        with pytest.raises(VibeSoundClientError, match="not JSON"):
            client.health()
        with pytest.raises(VibeSoundClientError, match="not an object"):
            client.health()
    finally:
        client.close()
