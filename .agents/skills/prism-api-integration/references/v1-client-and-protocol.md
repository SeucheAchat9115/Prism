# Prism v1 client and protocol

The runtime discovery endpoints and models in
`src/prism/application/types.py` are authoritative. This reference maps them so
an agent can choose tools without rediscovering the whole server.

## Service boundary

Start one project service explicitly:

```powershell
uv run prism serve song.prism-work --host 127.0.0.1 --port 8765
```

The default base URL is `http://127.0.0.1:8765`. CLI resolution order is:
explicit `--url`, `PRISM_URL`, then the default. CLI URLs must be absolute
HTTP(S) loopback URLs without credentials, path, query, or fragment.

The server accepts local Host values and same-origin HTTP/WebSocket requests.
It has no authentication and must not be exposed as a remote API. JSON bodies
are bounded to 16 MiB; uploads use separately bounded streaming staging.

## Discovery first

| Purpose | Route | Client |
| --- | --- | --- |
| Liveness | `GET /api/v1/health` | `health()` |
| Project readiness/identity | `GET /api/v1/readiness` | `readiness()` |
| Application/API version | `GET /api/v1/version` | `version()` |
| Feature flags and limits | `GET /api/v1/capabilities` | `capabilities()` |
| Current request JSON schemas | `GET /api/v1/schemas` | `schemas()` |
| Native synth preset catalog | `GET /api/v1/synth/presets` | `synth_presets()` |
| OpenAPI UI | `GET /docs` | Browser/manual inspection |
| OpenAPI JSON | `GET /openapi.json` | Protocol tooling |

Readiness returns `project_id` and current `revision`. A service rejects another
project UUID with `project_not_found`.

## Typed Python quickstart

```python
from prism.api import PrismClient, PrismClientError

try:
    with PrismClient("http://127.0.0.1:8765", timeout=30.0) as client:
        health = client.health()
        ready = client.readiness()
        version = client.version()
        capabilities = client.capabilities()
        schemas = client.schemas()
        project = client.get_project(ready.project_id)
        state = client.get_state(ready.project_id)
except PrismClientError as error:
    details = [issue.model_dump(mode="json") for issue in error.issues]
    raise RuntimeError({"status": error.status_code, "errors": details}) from error
```

`PrismClientError.status_code == 0` means a transport failure. Other failures
contain stable `ApiIssue` objects. Use context managers so the underlying HTTP
client and WebSocket close deterministically.

## Client method map

### Read and discovery

- `health()`, `readiness()`, `version()`, `capabilities()`, `schemas()`
- `get_project(project_id)`, `get_state(project_id)`,
  `validate_project(project_id)`
- `list_tracks`, `list_scenes`, `list_clips`, `list_assets`, `list_slots`
- `resolve_name(project_id, entity_type, name)`

### Authoring and uploads

- `preview_transaction(project_id, request)`
- `commit_transaction(project_id, request)`
- `upload_audio(project_id, source, filename=None, upload_id=None)`
- `discard_upload(project_id, upload_id)`
- `synth_presets()`
- `generate_synth_asset(project_id, request, preview=False)`
- `resolve_external_change(project_id)`

### Runtime

- `transport(project_id, request)`
- `launch_slot(project_id, request)`
- `stop_track(project_id, request)`
- `list_devices()`, `restart_audio(device=None)`
- `events(project_id)`

### Jobs

- `preview_render`, `submit_render`, `preview_export`, `submit_export`
- `list_jobs`, `get_job`, `cancel_job`, `wait_for_job`

Use `$prism-project-authoring`, `$prism-session-control`, and
`$prism-render-export` for the semantic rules behind those methods.

## HTTP route map

### Project inspection

| Method | Route | Response focus |
| --- | --- | --- |
| `GET` | `/api/v1/projects/{id}` | `project` |
| `GET` | `/api/v1/projects/{id}/state` | Runtime snapshot |
| `GET` | `/api/v1/projects/{id}/validation` | Layered validation |
| `GET` | `/api/v1/projects/{id}/tracks` | `tracks` |
| `GET` | `/api/v1/projects/{id}/scenes` | `scenes` |
| `GET` | `/api/v1/projects/{id}/clips` | `clips` |
| `GET` | `/api/v1/projects/{id}/assets` | `assets` |
| `GET` | `/api/v1/projects/{id}/slots` | `slots` |
| `GET` | `/api/v1/projects/{id}/resolve?entity_type=...&name=...` | Resolved UUID |

### Authoring

| Method | Route | Body/result |
| --- | --- | --- |
| `POST` | `/api/v1/projects/{id}/uploads` | Multipart `file`, optional `upload_id`; staged upload |
| `DELETE` | `/api/v1/projects/{id}/uploads/{upload_id}` | Discard staging |
| `POST` | `/api/v1/projects/{id}/transactions/preview` | `TransactionRequest` / `TransactionResult` |
| `POST` | `/api/v1/projects/{id}/transactions` | Commit same contract |
| `GET` | `/api/v1/synth/presets` | Built-in preset metadata and default sequences |
| `POST` | `/api/v1/projects/{id}/synth-assets?preview=...` | `SynthAssetRequest` / `SynthAssetResult` |
| `POST` | `/api/v1/projects/{id}/external-change/resolve` | `{"resolution":"detach_source"}` |

### Runtime and jobs

| Method | Route |
| --- | --- |
| `POST` | `/api/v1/projects/{id}/transport` |
| `POST` | `/api/v1/projects/{id}/session/launch` |
| `POST` | `/api/v1/projects/{id}/session/stop` |
| `POST` | `/api/v1/projects/{id}/clips/{clip_id}/launch` |
| `POST` | `/api/v1/projects/{id}/clips/{clip_id}/stop` |
| `GET` | `/api/v1/audio/devices` |
| `POST` | `/api/v1/audio/restart` |
| `POST` | `/api/v1/projects/{id}/render-jobs/preview` |
| `POST` | `/api/v1/projects/{id}/render-jobs` |
| `POST` | `/api/v1/projects/{id}/export-jobs/preview` |
| `POST` | `/api/v1/projects/{id}/export-jobs` |
| `GET` | `/api/v1/projects/{id}/jobs` |
| `GET` | `/api/v1/projects/{id}/jobs/{job_id}` |
| `DELETE` | `/api/v1/projects/{id}/jobs/{job_id}` |
| `WS` | `/api/v1/projects/{id}/events` |

`POST /api/v1/projects/{id}/render` is a synchronous compatibility route.
Prefer preview plus background render jobs for agent workflows.

## Raw HTTP example

```python
import httpx

base_url = "http://127.0.0.1:8765"
with httpx.Client(base_url=base_url, timeout=30.0) as http:
    ready_response = http.get("/api/v1/readiness")
    ready_response.raise_for_status()
    ready = ready_response.json()
    project_id = ready["project_id"]

    validation_response = http.get(f"/api/v1/projects/{project_id}/validation")
    validation_response.raise_for_status()
    validation = validation_response.json()
```

For mutations, serialize the schema returned by `/api/v1/schemas`; do not add
unknown fields. Send `Accept: application/json`. If an Origin header is used,
it must exactly match the local scheme and host.

## Errors and retry behavior

Ordinary API failures use:

```json
{
  "ok": false,
  "errors": [
    {"code": "stable_code", "path": "/field", "message": "Explanation"}
  ]
}
```

Request validation is HTTP 422. Conflicts such as stale revision, required
cascade/reset, idempotency conflict, and external project change use HTTP 409.
Other endpoints may return 404, 413, 429, 500, or 503 according to the stable
issue code.

`PrismClient` raises `PrismClientError` for transport failures and ordinary
error envelopes. Transaction preview/commit deliberately return a typed
`TransactionResult` even when the HTTP status is an error, so check `result.ok`,
`result.committed`, `result.errors`, and current revision.

Native synth generation also returns its typed `SynthAssetResult` on a rejected
transaction. Check `result.ok` and `result.transaction.errors`. Use the same
request and idempotency key for an unknown retry; changing the sound under that
key is an idempotency conflict.

Retry rules:

- Safe reads may retry with a bounded policy.
- A stale write requires refetch/reconciliation and a new preview.
- Retry an unknown transaction outcome only with the identical operations and
  idempotency key.
- Retry a render/export submission only with the identical request and key.
- WebSockets do not silently reconnect; resync state before reopening.
- Never make an unbounded polling or retry loop.

## CLI as an agent tool

Finite commands with `--json` emit exactly one object:

```json
{
  "cli_schema_version": 1,
  "ok": true,
  "command": "project state",
  "project": {"path": "song.prism-work", "id": "<uuid>", "revision": 2},
  "dry_run": false,
  "data": {},
  "warnings": [],
  "errors": []
}
```

Parse `cli_schema_version`, `ok`, `data`, and structured errors. Do not scrape
human output. Stable exit classes are 0 success, 2 usage, 3 validation, 4
conflict, 5 I/O, 6 service, 7 audio, 8 job, 70 internal, and 130 interrupted.
Typer argument errors use exit 2 before a JSON envelope can exist.
