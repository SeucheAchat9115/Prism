# Phase 6 command-line contracts

Phase 6 makes the complete proof-of-concept workflow available to people and
coding agents without a browser. With the explicit exceptions of local project
creation, portable inspection, migration, and server startup, commands are
clients of the stable loopback `/api/v1` service. They do not edit a working
manifest directly.

## Service lifecycle and project identity

Start one foreground service for one project:

```text
prism serve PROJECT [--host 127.0.0.1] [--port 8765] [--open]
```

There is no automatic background daemon. Startup output is emitted only after
the listening socket is bound, and Ctrl+C performs normal application-service
cleanup. `--dry-run` validates the project, host, and port without taking the
writer lock or binding a socket.

Every service command accepts `--url`. Its value is selected in this order:

1. Explicit `--url`.
2. `PRISM_URL`.
3. `http://127.0.0.1:8765`.

Only absolute HTTP(S) loopback URLs without credentials, paths, queries, or
fragments are accepted. Before a project-scoped request is made, the CLI reads
the local project identity without taking its writer lock and compares that UUID
with `/api/v1/readiness`. A mismatch exits as a conflict rather than sending the
command to the wrong service.

`project show` and `project validate` use the service by default. Their
`--portable` form is deliberately offline and reads only an immutable
`.prism` archive. `project migrate` similarly works only on a portable
archive and refuses to rewrite it while an adjacent working sidecar exists.

## Command surface

```text
prism serve PROJECT [--host HOST] [--port PORT] [--open] [--dry-run] [--json]

prism server status PROJECT
prism server capabilities PROJECT
prism server schemas PROJECT

prism project init PATH [--dry-run]
prism project show PROJECT [--portable]
prism project validate PROJECT [--portable]
prism project state PROJECT
prism project migrate ARCHIVE [--dry-run]
prism project export PROJECT --output NAME [--no-wait] [--dry-run]
prism project detach-source PROJECT [--dry-run]

prism entity list PROJECT {track|scene|clip|asset|slot}
prism entity resolve PROJECT {track|scene|clip|asset} NAME

prism audio import PROJECT FILE [--idempotency-key KEY] [--dry-run]
prism asset import PROJECT FILE [--idempotency-key KEY] [--dry-run]
prism audio devices PROJECT
prism audio restart PROJECT [--device DEVICE] [--dry-run]

prism transport play PROJECT [--dry-run]
prism transport pause PROJECT [--dry-run]
prism transport stop PROJECT [--dry-run]
prism transport reset PROJECT [--dry-run]

prism session launch PROJECT --track SELECTOR --scene SELECTOR [--dry-run]
prism session stop PROJECT --track SELECTOR [--dry-run]

prism transaction preview PROJECT OPS_FILE
prism transaction commit PROJECT OPS_FILE [--dry-run]

prism render PROJECT (--bars N | --seconds N) [--commands FILE]
                 [--output NAME] [--no-wait] [--dry-run]

prism job list PROJECT
prism job show PROJECT JOB_ID
prism job wait PROJECT JOB_ID [--timeout SECONDS]
prism job cancel PROJECT JOB_ID [--dry-run]

prism events watch PROJECT [--count N] [--timeout SECONDS] [--json]
```

`asset import` is a compatibility alias for `audio import`. Import creates only
an asset; clips and slot assignments remain explicit transaction operations.
This avoids hidden structural changes and lets an agent preview the complete
graph edit.

Track, scene, clip, and asset selectors accept either a UUID or a unique exact
case-insensitive name. Name resolution rejects missing and ambiguous matches.
Job IDs remain UUID-only. Render and export output names are always resolved
inside the working project's `exports/` root.

## Transactions and render commands

A transaction file may be a complete `TransactionRequest`:

```json
{
  "base_revision": 4,
  "idempotency_key": "producer-pass-2",
  "allow_runtime_reset": false,
  "operations": [
    {"op": "track.create", "name": "Drums"}
  ]
}
```

It may also be a bare operation array. In that form, the CLI uses the revision
reported by readiness unless `--base-revision` is supplied:

```json
[
  {"op": "track.create", "name": "Drums"},
  {"op": "scene.create", "name": "Verse"}
]
```

CLI flags override the corresponding full-request fields when explicitly
provided. Input is UTF-8 JSON, bounded to 16 MiB, and validated with the same
strict Pydantic contracts advertised by `server schemas`.

`render --commands FILE` accepts an ordered array of render commands. Exactly
one of `--bars` and `--seconds` is required. Render and export submit background
jobs and wait by default. `--no-wait` returns the accepted job immediately.
Human-mode polling writes progress to stderr; JSON mode remains silent until it
can emit one final envelope.

## Dry-run guarantees

Dry runs perform the strongest available validation while leaving durable and
runtime state unchanged:

| Command family | Dry-run behavior |
| --- | --- |
| `project init`, `project migrate` | Validate names, paths, schemas, and conflicts without writing |
| `serve` | Validate local identity and bind policy without opening the service |
| `transaction commit` | Call the server transaction-preview endpoint |
| `audio import` | Stage and decode the upload, preview its import transaction, then always discard staging |
| `render`, `project export` | Resolve and validate the output policy without enqueueing a job or creating output |
| transport, session, restart, detach, cancel | Resolve selectors and inspect the target without sending a mutating request |

`transaction preview` is inherently a dry run and reports `dry_run: true` in its
machine envelope.

For retry-safe audio imports, a supplied idempotency key and the source content
hash derive stable upload and asset UUIDs. Transaction retry comparison ignores
the caller's refreshed base revision while still comparing the complete
operation batch, so a lost successful response can be replayed but reusing the
key for different audio is rejected.

## Machine output

Finite commands accept `--json` and emit exactly one compact JSON object to
stdout after argument parsing:

```json
{
  "cli_schema_version": 1,
  "ok": true,
  "command": "transaction commit",
  "project": {
    "path": "C:\\music\\song.prism-work",
    "id": "9ee9b55c-1fc7-43e7-a753-a40c6cb1ee42",
    "revision": 5
  },
  "dry_run": false,
  "data": {},
  "warnings": [],
  "errors": []
}
```

Known failures use the same envelope, set `ok` to false, and put stable
`ApiIssue` values in `errors`. Native Typer parsing failures retain Typer's usage
format and exit code 2 because no valid `--json` state exists yet.

`events watch --json` is the intentional streaming exception: it emits one raw
`EventEnvelope` per JSONL line. The synchronous WebSocket client has a 1 MiB
message limit and a 16-message local queue, sends the same loopback origin, does
not use a proxy, and does not reconnect silently. `--count` makes bounded scripts
possible; `--timeout` is an inactivity deadline.

## Exit codes

| Code | Meaning |
| ---: | --- |
| 0 | Success |
| 2 | Usage, local JSON, or local schema error |
| 3 | Validation failure, missing entity, or rejected operation |
| 4 | Revision, lock, external-change, idempotency, or project-identity conflict |
| 5 | Filesystem, archive, persistence, or output I/O failure |
| 6 | Service transport or server failure |
| 7 | Audio runtime or device failure |
| 8 | Job, render, export, cancellation, or wait timeout failure |
| 70 | Unexpected internal CLI failure |
| 130 | User interruption |

## Verification

The device-free automated workflow is:

```text
uv run python examples/05_cli_agent_workflow.py
uv run pytest -m "not audio_device" --cov --cov-report=term-missing
uv run mypy src/prism
uv run ruff check .
uv build --no-sources
```

Example 05 starts the real installed `prism serve` command, waits for
readiness, exercises the public CLI, shuts the process down, and reopens the
exported portable archive. The service-backed CLI integration test uses the same
FastAPI contracts with the deterministic fake audio backend.
