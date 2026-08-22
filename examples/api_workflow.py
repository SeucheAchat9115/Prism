"""Exercise the Phase 5 service and API without starting a network server."""

from __future__ import annotations

from _support import make_archive_fixture, parse_output_dir, print_json
from fastapi.testclient import TestClient

from vibesound.api import create_app
from vibesound.application import ApplicationService, TransportRequest
from vibesound.audio import FakeAudioBackend


def main() -> int:
    run_dir = parse_output_dir(
        "api-workflow",
        "Run the local application service and API workflow without hardware.",
    )
    project_path, project, track, scene, clip = make_archive_fixture(
        run_dir,
        sample_rate=8000,
        seconds=1.0,
        loop=True,
    )
    service = ApplicationService(project_path, backend_factory=FakeAudioBackend)
    client = TestClient(create_app(service))
    project_id = str(project.project_id)
    try:
        state = client.get(f"/api/v1/projects/{project_id}/state").json()
        transaction = {
            "base_revision": state["revision"],
            "operations": [
                {
                    "op": "set",
                    "path": f"/tracks/{track.id}/mixer/gain_db",
                    "value": -3.0,
                }
            ],
        }
        preview = client.post(
            f"/api/v1/projects/{project_id}/transactions/preview",
            json=transaction,
        ).json()
        commit = client.post(
            f"/api/v1/projects/{project_id}/transactions",
            json=transaction,
        ).json()
        stale = client.post(
            f"/api/v1/projects/{project_id}/transactions",
            json=transaction,
        ).json()

        with client.websocket_connect(f"/api/v1/projects/{project_id}/events") as socket:
            service.transport(TransportRequest(operation="play"))
            event = socket.receive_json()

        launch = client.post(
            f"/api/v1/projects/{project_id}/clips/{clip.id}/launch",
            json={"track_id": str(track.id), "scene_id": str(scene.id)},
        ).json()
        render = client.post(
            f"/api/v1/projects/{project_id}/render",
            json={
                "output_path": str(run_dir / "api-render.wav"),
                "seconds": 1.0,
                "commands": [
                    {
                        "frame": 0,
                        "operation": "launch_scene",
                        "scene_id": str(scene.id),
                    }
                ],
            },
        ).json()
        print_json(
            {
                "project_path": str(project_path),
                "preview_committed": preview["committed"],
                "commit_revision": commit["after_revision"],
                "stale_error": stale["errors"][0]["code"],
                "event_type": event["type"],
                "launch_changed": launch["action"]["changed"],
                "render_output": render["metadata"]["output_path"],
            }
        )
        return 0
    finally:
        service.close()


if __name__ == "__main__":
    raise SystemExit(main())
