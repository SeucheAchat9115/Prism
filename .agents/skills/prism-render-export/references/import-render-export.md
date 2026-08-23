# Imports, renders, exports, and jobs

## Audio import

The preferred one-shot command is:

```powershell
uv run prism audio import song.prism-work drums.wav `
  --idempotency-key drums-source-v1 --dry-run --json
uv run prism audio import song.prism-work drums.wav `
  --idempotency-key drums-source-v1 --json
```

`--dry-run` still streams, bounds, and decodes the upload, previews the asset
transaction, and discards staging. A keyed CLI import derives stable upload and
asset UUIDs from project ID, key, and source hash. Reusing the key for different
audio is rejected.

Import creates only an asset. It does not create a clip, track, scene, or slot.
Use an explicit transaction for those structural decisions.

The equivalent client lifecycle is:

1. `upload_audio(project_id, source, upload_id=...)`.
2. Preview and commit `AssetImportOperation` in a `TransactionRequest`.
3. Call `discard_upload` in a `finally` block.

Do not retain staging as durable state.

## Render request

`RenderJobRequest` fields:

| Field | Contract |
| --- | --- |
| `output_path` | Non-empty project-local name/path; default `render.wav` |
| `bars` | Positive integer; mutually exclusive with `seconds` |
| `seconds` | Positive finite number; mutually exclusive with `bars` |
| `commands` | Ordered list; default empty |
| `idempotency_key` | Optional 1–128 character retry key |

Render commands:

| Operation | Required IDs | Forbidden IDs |
| --- | --- | --- |
| `launch_slot` | `track_id`, `scene_id` | — |
| `launch_scene` | `scene_id` | `track_id` |
| `stop_track` | `track_id` | `scene_id` |
| `stop_all` | none | `track_id`, `scene_id` |

Every command has a non-negative `frame`. Commands must be ordered by
nondecreasing frame.

Example `render-commands.json`:

```json
[
  {"frame": 0, "operation": "launch_scene", "scene_id": "<scene-uuid>"},
  {"frame": 88200, "operation": "stop_all"}
]
```

CLI preview and submit:

```powershell
uv run prism render song.prism-work --bars 4 `
  --commands render-commands.json --output mix.wav --dry-run --json
uv run prism render song.prism-work --bars 4 `
  --commands render-commands.json --output mix.wav `
  --idempotency-key mix-v1 --json
```

The CLI waits by default. Use `--no-wait` only when the caller will retain the
job UUID and monitor it explicitly.

## Portable export

```powershell
uv run prism project export song.prism-work --output song.prism --dry-run --json
uv run prism project export song.prism-work --output song.prism --json
```

The output is a deterministic portable archive beneath the working project's
`exports/` directory. Verify it offline:

```powershell
uv run prism project show <reported-output-path> --portable --json
uv run prism project validate <reported-output-path> --portable --json
```

## Typed client workflow

```python
from prism.api import PrismClient
from prism.application import ExportJobRequest, RenderJobRequest

with PrismClient() as client:
    ready = client.readiness()
    request = RenderJobRequest.model_validate(
        {
            "bars": 1,
            "output_path": "agent-preview.wav",
            "idempotency_key": "agent-render-01",
            "commands": [],
        }
    )
    preview = client.preview_render(ready.project_id, request)
    job = client.submit_render(ready.project_id, request)
    terminal = client.wait_for_job(ready.project_id, job.job_id, timeout=300.0)
    if terminal.state != "completed":
        raise RuntimeError(terminal.error or terminal.state)
    if not terminal.output_path or not terminal.output_sha256:
        raise RuntimeError("Completed render lacks verified output metadata")

    export_request = ExportJobRequest(
        output_path="agent-snapshot.prism",
        idempotency_key="agent-export-01",
    )
    client.preview_export(ready.project_id, export_request)
```

`PrismClient.wait_for_job` returns any terminal state; it does not convert a
failed or cancelled job into an exception. Inspect `state`, `error`, output path,
and hash.

## Job API and lifecycle

| Purpose | Method and route | Client method |
| --- | --- | --- |
| Preview render | `POST /api/v1/projects/{id}/render-jobs/preview` | `preview_render` |
| Submit render | `POST /api/v1/projects/{id}/render-jobs` | `submit_render` |
| Preview export | `POST /api/v1/projects/{id}/export-jobs/preview` | `preview_export` |
| Submit export | `POST /api/v1/projects/{id}/export-jobs` | `submit_export` |
| List jobs | `GET /api/v1/projects/{id}/jobs` | `list_jobs` |
| Read job | `GET /api/v1/projects/{id}/jobs/{job_id}` | `get_job` |
| Cancel job | `DELETE /api/v1/projects/{id}/jobs/{job_id}` | `cancel_job` |

Job states are `queued`, `running`, `completed`, `failed`, and `cancelled`.
Each job records kind, project ID, accepted revision, progress, request, output
path/hash, timestamps, and a structured error.

Prism uses one worker with eight waiting slots. A full queue returns
`job_queue_full`. Render cancellation is checked at bounded frame intervals;
progress events are rate-limited. Terminal metadata is retained but should not
be treated as permanent external storage.

CLI monitoring:

```powershell
uv run prism job list song.prism-work --json
uv run prism job show song.prism-work <job-uuid> --json
uv run prism job wait song.prism-work <job-uuid> --timeout 300 --json
uv run prism job cancel song.prism-work <job-uuid> --dry-run --json
```

Use `events watch` or the client event stream when progress must be reactive.
Polling should be bounded by an explicit timeout.

## Artifact verification

For WAV output, verify at least:

- file exists at the job-reported path;
- SHA-256 equals `output_sha256`;
- sample rate and channels match the project/render contract;
- frame count or duration matches the request;
- deterministic rerendering where byte identity is an acceptance requirement.

For `.prism`, validate the archive through Prism and confirm the reopened
project ID, revision, assets, and structure. Do not validate only by ZIP-open
success.
