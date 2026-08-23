# Runtime controls and events

## Start and discover

```powershell
uv run prism demo demo.prism-work --open
# or
uv run prism serve song.prism-work --port 8765
```

The server stays in the foreground and normally serves
`http://127.0.0.1:8765`. Stop it with Ctrl+C. If using another port, pass
`--url` to every client command or set `PRISM_URL` to an absolute loopback URL.

Before control:

```powershell
uv run prism server status song.prism-work --json
uv run prism server capabilities song.prism-work --json
uv run prism project state song.prism-work --json
uv run prism project validate song.prism-work --json
```

The CLI compares the local project UUID with readiness and exits with a conflict
instead of sending a command to the wrong service.

## CLI controls

```powershell
uv run prism transport play song.prism-work --json
uv run prism transport pause song.prism-work --json
uv run prism transport stop song.prism-work --json
uv run prism transport reset song.prism-work --json

uv run prism session launch song.prism-work --track Drums --scene Verse --json
uv run prism session stop song.prism-work --track Drums --json

uv run prism audio devices song.prism-work --json
uv run prism audio restart song.prism-work --device 3 --dry-run --json
uv run prism events watch song.prism-work --count 20 --timeout 30 --json
```

Track and scene selectors accept UUIDs or unique exact case-insensitive names.
Finite `--json` commands emit one stable CLI envelope. `events watch --json` is
the exception and emits one raw `EventEnvelope` per JSONL line.

Use `--dry-run` to resolve and validate transport, session, or restart targets
without mutating runtime state. Real device restart is opt-in.

## Typed Python controls

```python
from prism.api import PrismClient
from prism.application import ClipLaunchRequest, ClipStopRequest, TransportRequest

with PrismClient("http://127.0.0.1:8765") as client:
    ready = client.readiness()
    project_id = ready.project_id
    track_id = client.resolve_name(project_id, "track", "Drums")
    scene_id = client.resolve_name(project_id, "scene", "Verse")

    client.transport(project_id, TransportRequest(operation="play"))
    launch = client.launch_slot(
        project_id,
        ClipLaunchRequest(track_id=track_id, scene_id=scene_id),
    )
    print(launch.accepted, launch.action.target_frame)
    client.stop_track(project_id, ClipStopRequest(track_id=track_id))
```

Use `get_state(project_id)` to obtain:

- project revision;
- engine mode, position frame, active clip IDs, and pending action frames;
- audio state, selected device, errors, underruns, render head, estimated
  audible head, and queued latency.

## Endpoint mapping

| Purpose | Method and route | Typed client |
| --- | --- | --- |
| Runtime snapshot | `GET /api/v1/projects/{id}/state` | `get_state` |
| Transport | `POST /api/v1/projects/{id}/transport` | `transport` |
| Launch track/scene slot | `POST /api/v1/projects/{id}/session/launch` | `launch_slot` |
| Stop a track | `POST /api/v1/projects/{id}/session/stop` | `stop_track` |
| Launch a known clip | `POST /api/v1/projects/{id}/clips/{clip_id}/launch` | Raw HTTP only |
| Stop a known clip | `POST /api/v1/projects/{id}/clips/{clip_id}/stop` | Raw HTTP only |
| List devices | `GET /api/v1/audio/devices` | `list_devices` |
| Restart audio | `POST /api/v1/audio/restart` | `restart_audio` |
| Events | `WS /api/v1/projects/{id}/events` | `events` |

Transport body:

```json
{"operation": "play"}
```

Allowed operations are `play`, `pause`, `stop`, and `reset`.

Session launch and stop bodies:

```json
{"track_id": "<uuid>", "scene_id": "<uuid>"}
{"track_id": "<uuid>"}
```

## Event stream

```python
from prism.api import PrismClient

with PrismClient() as client:
    ready = client.readiness()
    with client.events(ready.project_id) as events:
        event = events.receive(timeout=10.0)
        print(event.type, event.revision, event.payload)
```

The synchronous stream has a 1 MiB message limit and a bounded local queue. It
does not silently reconnect. Treat timeout separately from `PrismClientError`,
then re-read readiness/project/state before reopening a stream.

Relevant event families include:

- `project.changed`, `project.external_change`,
  `project.external_change_resolved`;
- `transport.changed`;
- `clip.scheduled`, `clip.stop_scheduled`, `clip.launched`, `clip.stopped`,
  `clip.completed`;
- `audio.device_fallback`, `audio.restarted`, `audio.error`;
- `job.queued`, `job.started`, `job.progress`, `job.completed`, `job.failed`,
  `job.cancelled`.

After reconnecting, perform a full resync; events are notifications, not an
authoritative event-sourced replay log.

## Browser behavior

The packaged page at `/` exposes transport, a scene-by-track grid, track stop,
mixer controls, render form, validation, and activity. Assets are under
`/assets/`; no Node build or third-party CDN is involved.

The browser retries a moving startup snapshot up to three times, buffers events
during startup, reconnects with capped backoff, and fully resyncs. Mixer edits
use typed transactions with idempotency and explicit stale-field conflict
resolution. Preserve those behaviors when testing or modifying the UI.
