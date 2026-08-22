from __future__ import annotations

from pathlib import Path

from application._helpers import make_archive_fixture
from fastapi.testclient import TestClient

from vibesound.api import create_app
from vibesound.application import ApplicationService, TransportRequest
from vibesound.audio import FakeAudioBackend


def test_api_exposes_project_transactions_controls_render_and_events(tmp_path: Path) -> None:
    project_path, project, track, scene, clip = make_archive_fixture(tmp_path)
    service = ApplicationService(project_path, backend_factory=FakeAudioBackend)
    client = TestClient(create_app(service))
    project_id = str(project.project_id)
    try:
        shown = client.get(f"/api/v1/projects/{project_id}")
        state = client.get(f"/api/v1/projects/{project_id}/state")

        assert shown.status_code == 200
        assert shown.json()["project"]["name"] == "Application fixture"
        assert state.status_code == 200
        assert state.json()["revision"] == project.revision.number

        transaction = {
            "base_revision": project.revision.number,
            "operations": [
                {
                    "op": "set",
                    "path": f"/tracks/{track.id}/mixer/gain_db",
                    "value": -6.0,
                }
            ],
        }
        preview = client.post(
            f"/api/v1/projects/{project_id}/transactions/preview",
            json=transaction,
        )
        committed = client.post(
            f"/api/v1/projects/{project_id}/transactions",
            json=transaction,
        )
        stale = client.post(
            f"/api/v1/projects/{project_id}/transactions",
            json=transaction,
        )

        assert preview.status_code == 200
        assert preview.json()["committed"] is False
        assert committed.status_code == 200
        assert committed.json()["after_revision"] == project.revision.number + 1
        assert stale.status_code == 409
        assert stale.json()["errors"][0]["code"] == "stale_revision"

        with client.websocket_connect(f"/api/v1/projects/{project_id}/events") as socket:
            service.transport(TransportRequest(operation="play"))
            event = socket.receive_json()
            assert event["type"] == "transport.changed"
            assert event["project_id"] == project_id

        launched = client.post(
            f"/api/v1/projects/{project_id}/clips/{clip.id}/launch",
            json={"track_id": str(track.id), "scene_id": str(scene.id)},
        )
        rendered = client.post(
            f"/api/v1/projects/{project_id}/render",
            json={
                "output_path": str(tmp_path / "api-render.wav"),
                "seconds": 1.0,
                "commands": [
                    {
                        "frame": 0,
                        "operation": "launch_scene",
                        "scene_id": str(scene.id),
                    }
                ],
            },
        )

        assert launched.status_code == 200
        assert launched.json()["action"]["changed"] is True
        assert rendered.status_code == 200
        assert rendered.json()["metadata"]["subtype"] == "FLOAT"
        assert Path(rendered.json()["metadata"]["output_path"]).is_file()
    finally:
        service.close()


def test_api_returns_structured_errors_for_unknown_project_and_invalid_request(
    tmp_path: Path,
) -> None:
    project_path, project, _, _, _ = make_archive_fixture(tmp_path)
    service = ApplicationService(project_path, backend_factory=FakeAudioBackend)
    client = TestClient(create_app(service))
    try:
        missing = client.get("/api/v1/projects/00000000-0000-0000-0000-000000000000")
        invalid = client.post(
            f"/api/v1/projects/{project.project_id}/transactions",
            json={"base_revision": 0, "operations": []},
        )

        assert missing.status_code == 404
        assert missing.json()["errors"][0]["code"] == "project_not_found"
        assert invalid.status_code == 422
        assert invalid.json()["errors"][0]["code"] == "invalid_request"
    finally:
        service.close()
