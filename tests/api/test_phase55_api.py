from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from project._helpers import write_wav

from vibesound.api import create_app
from vibesound.application import ApplicationService
from vibesound.audio import FakeAudioBackend
from vibesound.project import create_project


def test_discovery_security_upload_and_typed_authoring(tmp_path: Path) -> None:
    project_path = tmp_path / "api55.vibesound"
    project = create_project(project_path, "API 5.5", sample_rate=8000)
    service = ApplicationService(project_path, backend_factory=FakeAudioBackend)
    app = create_app(service)
    client = TestClient(app)
    try:
        openapi = app.openapi()
        assert {
            "/api/v1/capabilities",
            "/api/v1/schemas",
            "/api/v1/projects/{project_id}/uploads",
            "/api/v1/projects/{project_id}/transactions",
            "/api/v1/projects/{project_id}/render-jobs",
            "/api/v1/projects/{project_id}/export-jobs",
        }.issubset(openapi["paths"])
        operations_schema = openapi["components"]["schemas"]["TransactionRequest"][
            "properties"
        ]["operations"]
        assert operations_schema["maxItems"] == 256
        assert client.get("/api/v1/health").json()["status"] == "healthy"
        assert client.get("/api/v1/readiness").json()["status"] == "ready"
        assert client.get("/api/v1/version").json()["api_version"] == "v1"
        assert client.get("/api/v1/capabilities").json()["authoring"]["typed_operations"]
        assert "transaction_request" in client.get("/api/v1/schemas").json()

        rejected_host = client.get("/api/v1/health", headers={"host": "evil.example"})
        rejected_origin = client.get(
            "/api/v1/health",
            headers={"origin": "https://evil.example"},
        )
        assert rejected_host.status_code == 400
        assert rejected_host.json()["errors"][0]["code"] == "host_rejected"
        assert rejected_origin.status_code == 403
        assert rejected_origin.json()["errors"][0]["code"] == "origin_rejected"

        source = tmp_path / "upload.wav"
        payload = write_wav(source)
        uploaded = client.post(
            f"/api/v1/projects/{project.project_id}/uploads",
            files={"file": (source.name, payload, "audio/wav")},
        )
        assert uploaded.status_code == 201
        upload = uploaded.json()["upload"]
        assert "path" not in upload

        track_id, scene_id, asset_id, clip_id = [uuid4() for _ in range(4)]
        committed = client.post(
            f"/api/v1/projects/{project.project_id}/transactions",
            json={
                "base_revision": 0,
                "idempotency_key": "api-build-1",
                "operations": [
                    {"op": "track.create", "track_id": str(track_id), "name": "Track"},
                    {"op": "scene.create", "scene_id": str(scene_id), "name": "Scene"},
                    {
                        "op": "asset.import",
                        "upload_id": upload["upload_id"],
                        "asset_id": str(asset_id),
                    },
                    {
                        "op": "clip.create",
                        "clip_id": str(clip_id),
                        "name": "Clip",
                        "asset_id": str(asset_id),
                    },
                    {
                        "op": "slot.assign",
                        "track_id": str(track_id),
                        "scene_id": str(scene_id),
                        "clip_id": str(clip_id),
                    },
                ],
            },
        )
        assert committed.status_code == 200
        assert committed.json()["created_ids"]["tracks"] == [str(track_id)]
        for collection in ("tracks", "scenes", "clips", "assets", "slots"):
            response = client.get(
                f"/api/v1/projects/{project.project_id}/{collection}"
            ).json()
            assert len(response[collection]) == 1
        validation = client.get(
            f"/api/v1/projects/{project.project_id}/validation"
        ).json()
        assert validation["stages"]["playback_readiness"]["ok"]
        resolved = client.get(
            f"/api/v1/projects/{project.project_id}/resolve",
            params={"entity_type": "track", "name": "track"},
        )
        assert resolved.json()["id"] == str(track_id)

        reset_preview = client.post(
            f"/api/v1/projects/{project.project_id}/transactions/preview",
            json={
                "base_revision": 1,
                "operations": [{"op": "transport.update", "sample_rate": 16000}],
            },
        )
        assert reset_preview.json()["runtime_reset_required"]
        assert client.get("/api/v1/audio/devices").status_code == 200
        assert client.post("/api/v1/audio/restart", json={"device": None}).status_code == 200
        detached = client.post(
            f"/api/v1/projects/{project.project_id}/external-change/resolve",
            json={"resolution": "detach_source"},
        )
        assert detached.status_code == 200

        too_large = client.post(
            f"/api/v1/projects/{project.project_id}/transactions",
            content=b"{}",
            headers={"content-length": str(16 * 1024 * 1024 + 1)},
        )
        invalid_length = client.post(
            f"/api/v1/projects/{project.project_id}/transactions",
            content=b"{}",
            headers={"content-length": "invalid"},
        )
        assert too_large.status_code == 413
        assert invalid_length.status_code == 400
    finally:
        service.close()


def test_async_job_endpoints_and_output_confinement(tmp_path: Path) -> None:
    project_path = tmp_path / "jobs-api.vibesound"
    project = create_project(project_path, "Jobs", sample_rate=8000)
    service = ApplicationService(project_path, backend_factory=FakeAudioBackend)
    client = TestClient(create_app(service))
    try:
        escaped = client.post(
            f"/api/v1/projects/{project.project_id}/render-jobs",
            json={"output_path": "../escape.wav", "seconds": 0.01},
        )
        accepted = client.post(
            f"/api/v1/projects/{project.project_id}/render-jobs",
            json={"output_path": "safe.wav", "seconds": 0.01},
        )

        assert escaped.status_code == 422
        assert escaped.json()["errors"][0]["code"] == "output_policy_error"
        assert accepted.status_code == 202
        job_id = accepted.json()["job"]["job_id"]
        terminal = None
        for _ in range(100):
            response = client.get(
                f"/api/v1/projects/{project.project_id}/jobs/{job_id}"
            )
            terminal = response.json()["job"]
            if terminal["state"] in {"completed", "failed", "cancelled"}:
                break
        assert terminal is not None and terminal["state"] == "completed"
        assert terminal["output_sha256"]
        listed = client.get(f"/api/v1/projects/{project.project_id}/jobs")
        cancelled = client.delete(
            f"/api/v1/projects/{project.project_id}/jobs/{job_id}"
        )
        exported = client.post(
            f"/api/v1/projects/{project.project_id}/export-jobs",
            json={"output_path": "portable.vibesound"},
        )
        assert listed.status_code == 200
        assert cancelled.status_code == 200
        assert exported.status_code == 202
    finally:
        service.close()
