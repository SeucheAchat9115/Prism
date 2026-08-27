# Level 5 — control Prism with the typed Python API

Goal: discover the live project, inspect native synth presets, preview and
generate an asset, observe an event, launch the Chorus, and submit a render
through `PrismClient`.

Keep the Level 3 service running in Terminal A. In **Terminal B**:

```powershell
$SongProject = Join-Path (Get-Location) "prism-tutorial.prism-work"
uv run prism server status $SongProject --json
```

## 1. Create the controller

This command writes a small local learning script. It does not edit the Prism
package or the project manifest.

```powershell
@'
from __future__ import annotations

from prism.api import PrismClient
from prism.application import (
    ClipLaunchRequest,
    RenderJobRequest,
    SynthAssetRequest,
    TransportRequest,
)
from prism.synthesis import NativeSynthSpec


def main() -> None:
    with PrismClient("http://127.0.0.1:8765") as client:
        ready = client.readiness()
        project_id = ready.project_id
        print("project", project_id, "revision", ready.revision)

        capabilities = client.capabilities()
        print("native synth", capabilities["native_synth"])
        print("presets", [item.name for item in client.synth_presets()])

        request = SynthAssetRequest(
            base_revision=ready.revision,
            filename="agent-pluck.wav",
            spec=NativeSynthSpec(
                preset="lead",
                sequence=["C5", "-", "G4", "-"],
                bars=1,
                waveform="square",
                attack_ms=2.0,
                release_ms=60.0,
                gate=0.45,
                gain_db=-10.0,
            ),
            idempotency_key="tutorial-agent-pluck-v1",
        )
        preview = client.generate_synth_asset(project_id, request, preview=True)
        if not preview.ok:
            raise RuntimeError(preview.transaction.errors)
        generated = client.generate_synth_asset(project_id, request)
        if not generated.ok:
            raise RuntimeError(generated.transaction.errors)
        print("generated asset", generated.asset_id, generated.sha256)

        chorus_id = client.resolve_name(project_id, "scene", "Chorus")
        kick_id = client.resolve_name(project_id, "track", "Kick")
        with client.events(project_id) as events:
            client.transport(project_id, TransportRequest(operation="reset"))
            event = events.receive(timeout=5.0)
            print("event", event.type, event.payload)

        launch = client.launch_slot(
            project_id,
            ClipLaunchRequest(track_id=kick_id, scene_id=chorus_id),
        )
        print("launch accepted", launch.accepted, "target", launch.action.target_frame)
        client.transport(project_id, TransportRequest(operation="play"))
        client.transport(project_id, TransportRequest(operation="stop"))

        current = client.readiness()
        render_request = RenderJobRequest.model_validate(
            {
                "output_path": "python-chorus.wav",
                "bars": 2,
                "idempotency_key": "tutorial-python-render-v1",
                "commands": [
                    {"frame": 0, "operation": "launch_scene", "scene_id": chorus_id}
                ],
            }
        )
        preview_job = client.preview_render(project_id, render_request)
        print("render preview", preview_job.output_path, "revision", current.revision)
        job = client.submit_render(project_id, render_request)
        terminal = client.wait_for_job(project_id, job.job_id, timeout=300.0)
        if terminal.state != "completed":
            raise RuntimeError(terminal.error or terminal.state)
        print("rendered", terminal.output_path, terminal.output_sha256)


if __name__ == "__main__":
    main()
'@ | Set-Content -Encoding utf8 tutorial_agent.py
```

## 2. Run it

```powershell
uv run python tutorial_agent.py
```

The generated pluck is imported as an asset but not attached to a clip; that is
an intentional separation of responsibilities. Use a `clip.create` and
`slot.assign` transaction, as in Levels 1–3, when the agent decides where it
belongs.

## 3. Inspect the result through another interface

```powershell
uv run prism entity list $SongProject asset --json
uv run prism job list $SongProject --json
uv run prism project validate $SongProject --json
```

This demonstrates interface parity: the Python client changed state, and the
CLI immediately sees the same revision, asset, job, and validation result.

## 4. Discover raw HTTP only when needed

Non-Python clients should inspect contracts before hand-writing JSON:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/api/v1/readiness
Invoke-RestMethod http://127.0.0.1:8765/api/v1/capabilities
Invoke-RestMethod http://127.0.0.1:8765/api/v1/schemas
Invoke-RestMethod http://127.0.0.1:8765/api/v1/synth/presets
```

Checkpoint: you have used typed requests and responses, project identity,
preview/commit, events, live session control, and background job waiting.
