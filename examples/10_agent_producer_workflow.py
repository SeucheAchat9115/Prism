"""Simulate an agent inspecting, editing, rendering, and verifying a song."""

from __future__ import annotations

import hashlib

import soundfile as sf
from _support import make_music_fixture, parse_output_dir, print_json

from vibesound.application import ApplicationService, RenderJobRequest, TransactionRequest
from vibesound.audio import FakeAudioBackend
from vibesound.engine import TransportClock
from vibesound.project import load_project


def main() -> int:
    run_dir = parse_output_dir(
        "agent-producer",
        "Run a complete inspect, transact, render, and verify workflow.",
    )
    project_path, project, tracks, scenes, _ = make_music_fixture(run_dir)
    render_path = run_dir / "agent-render.wav"
    service = ApplicationService(project_path, backend_factory=FakeAudioBackend)
    subscription = service.subscribe()
    try:
        initial = service.get_snapshot()
        transaction = TransactionRequest.model_validate(
            {
                "base_revision": initial.revision,
                "operations": [
                    {"op": "set", "path": "/name", "value": "Agentic Demo Beat"},
                    {
                        "op": "set",
                        "path": "/transport/tempo_bpm",
                        "value": 126.0,
                    },
                    {
                        "op": "set",
                        "path": f"/tracks/{tracks['Bass'].id}/mixer/gain_db",
                        "value": -3.0,
                    },
                ],
            }
        )
        preview = service.preview_transaction(transaction)
        preview_state = service.get_snapshot()
        committed = service.commit_transaction(transaction)
        project_changed = subscription.get(timeout=1.0)

        edited_project = service.get_project()
        clock = TransportClock.from_transport(edited_project.transport)
        bar = int(clock.frames_per_bar)
        render_request = RenderJobRequest.model_validate(
            {
                "output_path": str(render_path),
                "bars": 8,
                "commands": [
                    {
                        "frame": 0,
                        "operation": "launch_scene",
                        "scene_id": str(scenes["Intro"].id),
                    },
                    {"frame": bar, "operation": "stop_all"},
                    {
                        "frame": bar,
                        "operation": "launch_scene",
                        "scene_id": str(scenes["Groove"].id),
                    },
                    {"frame": bar * 4, "operation": "stop_all"},
                    {
                        "frame": bar * 4,
                        "operation": "launch_scene",
                        "scene_id": str(scenes["Breakdown"].id),
                    },
                    {"frame": bar * 6, "operation": "stop_all"},
                    {
                        "frame": bar * 6,
                        "operation": "launch_scene",
                        "scene_id": str(scenes["Outro"].id),
                    },
                    {"frame": bar * 8, "operation": "stop_all"},
                ],
            }
        )
        metadata = service.render(render_request)
        render_events = [subscription.get(timeout=1.0).type for _ in range(2)]

        reopened = load_project(project_path)
        samples, sample_rate = sf.read(render_path, always_2d=True, dtype="float32")
        print_json(
            {
                "project_path": str(project_path),
                "project_id": str(project.project_id),
                "initial_revision": initial.revision,
                "preview": {
                    "ok": preview.ok,
                    "committed": preview.committed,
                    "revision_unchanged": preview_state.revision == initial.revision,
                },
                "commit": {
                    "ok": committed.ok,
                    "revision": committed.after_revision,
                    "event": project_changed.type,
                },
                "render": {
                    "output_path": str(metadata.output_path),
                    "events": render_events,
                    "sample_rate": sample_rate,
                    "channels": int(samples.shape[1]),
                    "frames": int(samples.shape[0]),
                    "sha256": hashlib.sha256(render_path.read_bytes()).hexdigest(),
                },
                "reopened": {
                    "name": reopened.name,
                    "revision": reopened.revision.number,
                    "tempo_bpm": reopened.transport.tempo_bpm,
                },
            }
        )
        return 0
    finally:
        subscription.close()
        service.close()


if __name__ == "__main__":
    raise SystemExit(main())
