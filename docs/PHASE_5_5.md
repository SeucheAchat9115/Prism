# Phase 5.5 application contracts

Phase 5.5 is implemented as the stabilization boundary for future CLI and
browser clients. The portable `.prism` file is now an interchange artifact;
normal edits use an adjacent inspectable sidecar.

## Working storage

Opening `demo.prism` creates or reuses `demo.prism-work/`:

```text
demo.prism-work/
├── project.json
├── assets/audio/<asset-id>.<extension>
├── history/<revision>.json
├── exports/
└── .prism/
    ├── repository.json
    ├── lock
    ├── staging/
    ├── cache/audio/
    └── jobs/
```

The source archive is fingerprinted and never changed by service transactions.
Metadata commits atomically replace `project.json`; immutable audio is copied
once. A second writer is rejected by the repository lock. A changed source or
working manifest pauses writes until the caller explicitly detaches the source.
Portable exports are streamed, atomic, and deterministic.

Archive import bounds member count, manifest size, individual and total expanded
size, compression ratio, encrypted members, symlinks, path traversal, duplicate
members, and case collisions. Multipart audio uploads are streamed into bounded,
expiring staging storage and become project assets only in a transaction.

## Typed authoring

`TransactionRequest` accepts at most 256 discriminated operations:

- `project.rename`
- `track.create`, `track.rename`, `track.reorder`, `track.delete`
- `scene.create`, `scene.rename`, `scene.reorder`, `scene.delete`
- `asset.import`, `asset.delete`
- `clip.create`, `clip.update`, `clip.duplicate`, `clip.delete`
- `slot.assign`, `slot.replace`, `slot.clear`
- `transport.update`, `mixer.update`
- backward-compatible `set`

Previews and commits return created, changed, and deleted UUIDs; changed paths;
complete cascade impact; validation issues; and one of `none`,
`incremental_refresh`, `transport_preserving_rebuild`, or `required_reset`.
Required resets must be previewed and committed with
`allow_runtime_reset=true`. Destructive operations with dependants similarly
require `cascade=true`. Exact case-insensitive name resolution rejects missing
and ambiguous names. Successful keyed transactions are retained for 30 days,
bounded to 10,000 idempotency records.

## Runtime and jobs

Mixer values update the live engine without recreating the backend. Compatible
graph rebuilds retain transport position, pending launches, and active clips.
The event stream distinguishes future `clip.scheduled` acceptance from actual
`clip.launched`, `clip.stopped`, and natural `clip.completed` transitions.
Snapshots expose render-head, estimated audible-head, and queued-latency frames.

Working audio is decoded into an immutable cache and sample-rate converted with
SoXR HQ. Metadata-only operations do not decode audio or touch that cache. If no
output device is usable, Prism continues with the device-free backend.
Isolated underruns are recoverable; eight underruns within five seconds fault the
backend and expose a structured diagnostic.

Renders and portable exports run in a one-worker queue with eight waiting slots.
Jobs capture the accepted revision and expose queued, running, completed, failed,
and cancelled states. Rendering checks cancellation every 4,096 frames and
publishes progress at no more than 10 Hz. Job metadata is retained for seven days
and capped at 1,000 terminal records. Outputs are confined to the working
project's `exports/` tree.

## Local API

The additive `/api/v1` API exposes health, readiness, application/API version,
capabilities, schemas, layered validation, entity collections, name resolution,
uploads, transactions, transport, clip control, devices, recovery, jobs, and
events. `PrismClient` is the typed synchronous Python client.

The POC server rejects non-loopback binds, unknown Host values, mismatched HTTP
and WebSocket origins, oversized JSON requests, unsafe export paths, transactions
over 256 operations, more than 32 event subscribers, and subscriber queues over
256 events. Failures use the common `{"ok": false, "errors": [...]}` envelope.

## Acceptance and verification

Run the installed, synthetic, device-free acceptance launcher with:

```text
prism demo demo.prism-work
```

Use `--no-serve` for package smoke tests. The engineering gate is:

```text
uv run pytest -m "not audio_device" --cov --cov-report=term-missing
uv run mypy src/prism
uv run ruff check .
uv build --no-sources
```

Coverage fails below 85% for the non-native package. The PortAudio callback
module is excluded from the aggregate percentage and remains covered by its
mocked lifecycle/underrun tests plus the opt-in real-device smoke test. CI runs
the device-free gate on Windows and Linux and installs the exact built wheel in
a clean Windows environment before invoking the demo.
