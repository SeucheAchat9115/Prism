# Transaction operations

The runtime schema at `GET /api/v1/schemas` and the models in
`src/prism/application/types.py` are authoritative. Unknown fields are rejected.
A transaction contains 1–256 operations.

## Request and result

```json
{
  "base_revision": 4,
  "idempotency_key": "agent-arrangement-2026-08-23-01",
  "allow_runtime_reset": false,
  "operations": [
    {"op": "track.create", "name": "Drums"},
    {"op": "scene.create", "name": "Verse"}
  ]
}
```

`base_revision` is mandatory in the API. The CLI also accepts a bare operation
array and fills the revision from readiness unless `--base-revision` is set.

Preview and commit return `TransactionResult`, including:

- `ok`, `committed`, and before/after/current revisions;
- changed paths and created, changed, and deleted UUIDs by entity type;
- cascade impact;
- runtime impact: `none`, `incremental_refresh`,
  `transport_preserving_rebuild`, or `required_reset`;
- `runtime_reset_required`, replay status, warnings, and stable errors.

Preview can succeed while declaring a required reset. The commit then requires
`allow_runtime_reset=true`. A failed preview or commit must leave the revision
and project content unchanged.

## Operation catalog

Every operation accepts optional `op_id` (1–128 characters). IDs created by an
operation may be supplied explicitly; otherwise Prism generates them.

| Operation | Required fields | Optional fields and constraints |
| --- | --- | --- |
| `project.rename` | `name` | Name length 1–200 |
| `track.create` | `name` | `track_id`, non-negative `order` |
| `track.rename` | `track_id`, `name` | — |
| `track.reorder` | `track_id`, non-negative `order` | — |
| `track.delete` | `track_id` | `cascade` defaults false |
| `scene.create` | `name` | `scene_id`, non-negative `order` |
| `scene.rename` | `scene_id`, `name` | — |
| `scene.reorder` | `scene_id`, non-negative `order` | — |
| `scene.delete` | `scene_id` | `cascade` defaults false |
| `asset.import` | staged `upload_id` | `asset_id` |
| `asset.delete` | `asset_id` | `cascade` defaults false |
| `clip.create` | `name`, `asset_id` | `clip_id`, `source_offset_frames >= 0`, `duration_frames > 0`, `gain_db` -60..12, `loop` |
| `clip.update` | `clip_id` plus at least one change | `name`, `asset_id`, offsets/duration, `clear_duration`, `gain_db` -60..12, `loop` |
| `clip.duplicate` | `clip_id` | `new_clip_id`, `name` |
| `clip.delete` | `clip_id` | `cascade` defaults false |
| `slot.assign` | `track_id`, `scene_id`, `clip_id` | `slot_id`; target must be empty |
| `slot.replace` | `track_id`, `scene_id`, `clip_id` | Replaces the target cell |
| `slot.clear` | `track_id`, `scene_id` | — |
| `transport.update` | At least one changed field | `tempo_bpm` 20..300, `sample_rate <= 192000`, numerator 1..32, denominator 1/2/4/8/16, quantization `none`/`beat`/`bar` |
| `mixer.update` | `track_id` plus at least one change | `gain_db` -60..12, `pan` -1..1, `muted`, `solo` |
| `set` | `path`, `value` | Backward-compatible path edit; avoid for new workflows |

`clip.update` cannot set `duration_frames` and `clear_duration=true` together.
Operation IDs must be unique inside one transaction. A transaction cannot use
legacy `set` on the same path twice.

## CLI workflow

Create an operation file such as `operations.json`, then run:

```powershell
uv run prism transaction preview song.prism-work operations.json --json
uv run prism transaction commit song.prism-work operations.json `
  --idempotency-key agent-arrangement-2026-08-23-01 --json
uv run prism project validate song.prism-work --json
```

Use `--allow-runtime-reset` only after preview reports that reset and the caller
accepts it. `transaction commit --dry-run` calls the preview endpoint.

Selectors in CLI entity/session commands accept a UUID or unique exact
case-insensitive name. Use these discovery commands instead of parsing display
text:

```powershell
uv run prism entity list song.prism-work track --json
uv run prism entity resolve song.prism-work track Drums --json
```

## Typed Python workflow

```python
from prism.api import PrismClient
from prism.application import TrackCreateOperation, TransactionRequest

with PrismClient() as client:
    ready = client.readiness()
    request = TransactionRequest(
        base_revision=ready.revision,
        idempotency_key="agent-track-create-01",
        operations=[TrackCreateOperation(op="track.create", name="Drums")],
    )
    preview = client.preview_transaction(ready.project_id, request)
    if not preview.ok:
        raise RuntimeError(preview.errors)
    if preview.runtime_reset_required:
        raise RuntimeError("Explicit runtime-reset approval is required")
    result = client.commit_transaction(ready.project_id, request)
    if not result.ok or not result.committed:
        raise RuntimeError(result.errors)
    validation = client.validate_project(ready.project_id)
    if not validation.ok:
        raise RuntimeError(validation.stages)
```

Use the client as a context manager. Transaction failures are returned as typed
`TransactionResult` error envelopes, so inspect `ok` and `errors` rather than
assuming every rejection raises `PrismClientError`.

## Project lifecycle commands

```powershell
uv run prism project init song.prism-work --json
uv run prism serve song.prism-work
uv run prism project show song.prism-work --json
uv run prism project validate song.prism-work --json
uv run prism project export song.prism-work --output song.prism --json
uv run prism project show <exported-path> --portable --json
uv run prism project validate <exported-path> --portable --json
```

Working-project show/validate commands use the service. Portable show/validate
are offline. Export output is confined beneath `song.prism-work/exports/` even
when a simple output name is supplied.
