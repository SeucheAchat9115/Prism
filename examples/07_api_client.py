"""Exercise the versioned local API through an in-process HTTP client."""

from __future__ import annotations

from _support import make_music_fixture, parse_output_dir, print_json
from fastapi.testclient import TestClient

from prism.api import create_app
from prism.application import ApplicationService
from prism.audio import FakeAudioBackend
from prism.engine import TransportClock


def main() -> int:
    run_dir = parse_output_dir(
        "api-client",
        "Run the local application service and API workflow without hardware.",
    )
    project_path, project, tracks, scenes, clips = make_music_fixture(run_dir)
    service = ApplicationService(project_path, backend_factory=FakeAudioBackend)
    client = TestClient(create_app(service))
    project_id = str(project.project_id)
    try:
        shown_response = client.get(f"/api/v1/projects/{project_id}")
        state_response = client.get(f"/api/v1/projects/{project_id}/state")
        shown_response.raise_for_status()
        state_response.raise_for_status()
        state = state_response.json()
        transaction = {
            "base_revision": state["revision"],
            "operations": [
                {
                    "op": "set",
                    "path": f"/tracks/{tracks['Bass'].id}/mixer/gain_db",
                    "value": -3.0,
                }
            ],
        }
        preview = client.post(
            f"/api/v1/projects/{project_id}/transactions/preview",
            json=transaction,
        )
        commit = client.post(
            f"/api/v1/projects/{project_id}/transactions",
            json=transaction,
        )
        stale = client.post(
            f"/api/v1/projects/{project_id}/transactions",
            json=transaction,
        )
        preview.raise_for_status()
        commit.raise_for_status()

        with client.websocket_connect(f"/api/v1/projects/{project_id}/events") as socket:
            transport_events = []
            for operation in ("play", "pause", "stop", "reset"):
                response = client.post(
                    f"/api/v1/projects/{project_id}/transport",
                    json={"operation": operation},
                )
                response.raise_for_status()
                transport_events.append(socket.receive_json()["type"])

            clip = clips["Groove:Kick"]
            launch = client.post(
                f"/api/v1/projects/{project_id}/clips/{clip.id}/launch",
                json={
                    "track_id": str(tracks["Kick"].id),
                    "scene_id": str(scenes["Groove"].id),
                },
            )
            launch.raise_for_status()
            launch_event = socket.receive_json()
            stop = client.post(
                f"/api/v1/projects/{project_id}/clips/{clip.id}/stop",
                json={"track_id": str(tracks["Kick"].id)},
            )
            stop.raise_for_status()
            stop_event = socket.receive_json()

        clock = TransportClock.from_transport(project.transport)
        bar = int(clock.frames_per_bar)
        render = client.post(
            f"/api/v1/projects/{project_id}/render",
            json={
                "output_path": str(run_dir / "api-render.wav"),
                "bars": 4,
                "commands": [
                    {
                        "frame": 0,
                        "operation": "launch_scene",
                        "scene_id": str(scenes["Groove"].id),
                    },
                    {"frame": bar * 2, "operation": "stop_all"},
                ],
            },
        )
        render.raise_for_status()
        print_json(
            {
                "project_path": str(project_path),
                "project_name": shown_response.json()["project"]["name"],
                "track_count": len(shown_response.json()["project"]["tracks"]),
                "preview_committed": preview.json()["committed"],
                "commit_revision": commit.json()["after_revision"],
                "stale_status": stale.status_code,
                "stale_error": stale.json()["errors"][0]["code"],
                "transport_events": transport_events,
                "launch_changed": launch.json()["action"]["changed"],
                "launch_event": launch_event["type"],
                "stop_changed": stop.json()["action"]["changed"],
                "stop_event": stop_event["type"],
                "render_output": render.json()["metadata"]["output_path"],
            }
        )
        return 0
    finally:
        service.close()


if __name__ == "__main__":
    raise SystemExit(main())
