# VibeSound Implementation Plan

This document turns the VibeSound concept into small, testable implementation
steps. The sequence is intentionally POC-first: establish a trustworthy project
and agent-control loop before adding the failure modes of MIDI, recording, and
third-party plugins.

For build, installation, release, and deployment decisions, see the
[deployment guide](DEPLOYMENT.md).

## Fixed product decisions

- **Platform:** Windows first; keep interfaces portable for later macOS/Linux
  backends.
- **Runtime:** Python 3.12 with `uv` and `pyproject.toml`.
- **Application shape:** one local Python process that owns the engine and serves
  a browser UI, CLI operations, and a local API.
- **Frontend:** HTML/CSS/vanilla JavaScript served by Python; no Node build
  system in the first releases.
- **Project storage:** a self-contained `.vibesound` ZIP archive containing
  `project.json` and embedded audio assets.
- **POC media:** audio clips first; MIDI comes later.
- **Agent control:** CLI plus a versioned HTTP/WebSocket API.
- **Mutation model:** validated transactions with dry-run previews, atomic
  commits, and project revision checks.
- **Plugin timing:** VST3 support starts after the POC.
- **Plugin safety:** plugin discovery and processing run in an isolated worker.
- **Network boundary:** bind to `127.0.0.1` by default; remote access and auth
  are later features.

## Example maintenance gate

The [`examples/`](../examples/README.md) folder is the manually runnable guide
to the implemented product surface. Every phase must keep it aligned with the
public APIs and workflows that are actually available.

For each phase implementation:

- Add or update at least one small happy-path example for the new capability.
- Update `examples/README.md` with the command, prerequisites, and expected
  output or artifact.
- Keep device-, browser-, and plugin-dependent examples opt-in and clearly
  separated from deterministic examples.
- Add or update device-free smoke coverage in `tests/test_examples.py` where
  the example can run without external hardware.
- Do not document future API, browser, or VST behavior as a runnable example
  before that phase is implemented.

## Phase 0 — Repository and development foundation ✅ Complete

**Completed:** 2026-08-21

The repository foundation, local verification commands, and Windows CI workflow
are implemented and passing.

### Components

1. [x] Clone the empty `SeucheAchat9115/VibeSound` repository into the workspace.
2. [x] Create the first `main` branch and bootstrap commit.
3. [x] Add `pyproject.toml` with Python 3.12 metadata, runtime dependencies, and
   development commands.
4. [x] Add the `src/vibesound/` package layout.
5. [x] Add a minimal `vibesound` CLI with `--help` and `version`.
6. [x] Add `tests/`, `.gitignore`, and the initial smoke test.
7. [x] Add formatting, linting, and test configuration.
8. [x] Add Windows CI for tests that do not require an audio device in
   `.github/workflows/ci.yml`.

### Exit criteria

- [x] A clean checkout can create an environment with `uv sync --extra dev`.
- [x] `uv run python -m vibesound --help` succeeds.
- [x] `uv run pytest` succeeds without an audio device.
- [x] `uv run ruff check .` succeeds.

### Verification

- Local Windows verification passed on 2026-08-21.
- GitHub Actions runs the same test, lint, and CLI smoke checks on
  `windows-latest` for pushes to `main` and pull requests.

## Phase 1 — Project model and persistence ✅ Complete

**Completed:** 2026-08-21

Phase 1 implements a strict project schema and self-contained ZIP persistence
layer. Playback, rendering, API transactions, and the browser UI remain later
phases.

### Archive contract

Each project is a ZIP archive with a `.vibesound` extension:

```text
demo.vibesound
├── project.json
└── assets/
    └── audio/
        └── <asset-uuid>.<extension>
```

Archive guarantees:

- `project.json` exists exactly once at the archive root.
- Internal paths are safe relative POSIX paths.
- Absolute paths, traversal, duplicate members, and ZIP symlinks are rejected.
- Audio is copied into the archive rather than referenced externally.
- JSON and ZIP members are written deterministically.
- Existing asset bytes are preserved during rewrites.
- Saves write a temporary sibling archive and replace the destination atomically.

### Components

1. [x] Define strict Pydantic models for `Project`, `Track`, `Scene`,
   `AudioClip`, `ClipSlot`, `AssetReference`, `MixerState`, `TransportState`,
   and `ProjectRevision`.
2. [x] Add `schema_version` and UUID-based stable IDs.
3. [x] Implement project-level cross-reference validation with JSON-pointer
   error paths.
4. [x] Implement ZIP member safety validation and missing-asset detection.
5. [x] Implement deterministic manifest and archive serialization.
6. [x] Implement project creation, loading, saving, and reopening.
7. [x] Implement atomic archive replacement and failed-save preservation.
8. [x] Implement WAV/AIFF-compatible audio asset import with copied bytes,
   metadata, size, and SHA-256 tracking.
9. [x] Implement an explicit schema migration registry.
10. [x] Add CLI commands for project init/show/validate/migrate and asset import.
11. [x] Update the README and implementation plan to document `.vibesound`
    ZIP projects.

### Public persistence operations

```text
create_project(path, name, tempo_bpm=120, sample_rate=44100)
load_project(path)
save_project(path, project)
validate_project(path)
migrate_project(path)
import_audio(project_path, source_path)
```

Loading may apply registered migrations in memory, but only the explicit migrate
or save operation rewrites the archive. Future schema versions are rejected.

### CLI operations

```text
vibesound project init PATH [--name NAME] [--tempo BPM] [--sample-rate RATE]
vibesound project show PATH [--json]
vibesound project validate PATH [--json]
vibesound project migrate PATH
vibesound asset import PROJECT SOURCE [--json]
```

### Exit criteria

- [x] A project can be created, saved, loaded, validated, and reopened.
- [x] Equivalent projects produce deterministic archive bytes.
- [x] Invalid references produce actionable field-level errors.
- [x] Project saves preserve referenced audio member bytes.
- [x] A future schema migration can be registered without changing load callers.
- [x] Asset imports are portable, hashed, metadata-bearing, and atomic.
- [x] CLI project and asset commands work in human-readable and JSON modes.

### Verification

- Local Windows test suite: 13 passed on 2026-08-21.
- Ruff lint checks: passed on 2026-08-21.
- Tests cover model constraints, archive safety, deterministic output, asset
  import, hash validation, failed saves, migrations, and CLI workflows.

## Phase 2 — Deterministic session engine ✅ Complete

**Completed:** 2026-08-22

Phase 2 adds a thread-free, in-memory session engine. It snapshots and validates
the Phase 1 project model, consumes injected audio buffers, schedules session
actions on integer sample-frame boundaries, and returns deterministic stereo
buffers with typed events. It does not read project archives, mutate project
files, expose CLI/API commands, or open an audio device.

### Components

1. [x] Add the `vibesound.engine` package and typed runtime errors.
2. [x] Add immutable runtime snapshots, scheduled actions, engine steps, and
   transport/clip events.
3. [x] Implement exact sample-frame beat/bar conversion with time-signature-aware
   quantization.
4. [x] Implement validated mono/stereo float32 audio buffers and an injected
   in-memory source provider.
5. [x] Snapshot project indexes for tracks, scenes, clips, slots, and assets.
6. [x] Implement play, pause, stop, reset, and explicit frame advancement.
7. [x] Implement quantized slot, scene, track-stop, and stop-all scheduling.
8. [x] Enforce track-exclusive clips and deterministic stop-before-launch
   replacement behavior.
9. [x] Implement source offsets, durations, looping, and automatic clip stops.
10. [x] Implement clip/track gain, constant-power mono pan, stereo balance,
    mute, solo, and unclipped float headroom.
11. [x] Split rendering at exact mid-block event frames.
12. [x] Add a fake audio sink for device-free tests.

### Runtime contract

```text
SessionEngine(project, source_provider)
  play() / pause() / stop() / reset()
  launch_slot(track_id, scene_id)
  launch_scene(scene_id)
  stop_track(track_id) / stop_all()
  advance(frame_count) -> EngineStep
```

`EngineStep` contains the requested stereo `float32` buffer and events with
absolute sample-frame timestamps. The engine uses no wall-clock timing or
background thread. Sources must already match the project sample rate and
manifest channel/frame metadata; resampling is deferred to a later phase.

### Exit criteria

- [x] Identical inputs and command sequences produce identical samples, events,
  and final state.
- [x] Clip launches and stops occur on the expected quantization boundaries.
- [x] Gain, pan, mute, solo, looping, and clip replacement produce expected
  buffer values and event order.
- [x] Mid-block events split output at exact sample frames.
- [x] The engine runs fully without a physical audio device or archive I/O.

### Verification

- Full Windows test suite: 38 passed on 2026-08-22.
- Ruff lint checks: passed on 2026-08-22.
- Tests cover timing, time signatures, quantization, source validation, clip
  regions, looping, event ordering, block-size invariance, mixer behavior,
  mute/solo, stop-all, reset, and the fake sink.

## Phase 3 — Offline renderer ✅ Complete

**Completed:** 2026-08-22

Phase 3 adds a deterministic, device-free renderer. It can render a loaded
project with injected sources or validate and render a self-contained archive.
It reuses the Phase 2 scheduler and mixer, prepares a private project snapshot
for sample-rate conversion, and atomically writes stereo float32 WAV output.
The renderer does not add CLI/API routes, real-time audio, plugin processing,
or project-file mutations.

### Components

1. [x] Add frozen `RenderRequest`, `RenderCommand`, and `RenderMetadata`
   contracts with positive bars/seconds validation and ordered commands.
2. [x] Convert bars with tempo/time-signature-aware frame math and seconds by
   ceiling to the next project sample frame.
3. [x] Reuse `SessionEngine` for clip scheduling, mixing, gain, pan, mute,
   solo, looping, and natural clip stops.
4. [x] Apply launch, scene, track-stop, and stop-all commands at exact absolute
   frames with a fixed 4096-frame internal block size.
5. [x] Read and hash-check every referenced archive asset before output starts.
6. [x] Decode supported audio through `soundfile` and validate sample rate,
   channel count, frame count, and container format against the manifest.
7. [x] Add deterministic NumPy linear resampling to the project rate while
   preserving mono/stereo layout and converting clip offsets/durations.
8. [x] Write explicit `WAV`/`FLOAT` stereo output with project sample rate and
   preserve unclipped float headroom.
9. [x] Return project ID, revision, path, format, subtype, sample rate,
   channels, frame count, and duration metadata.
10. [x] Validate projects, requests, commands, sources, and destination paths
    before creating an output temporary file.
11. [x] Commit output through a flushed and fsynced sibling temporary file with
    cleanup on failure and preservation of an existing destination.

### Public rendering contract

```text
render(project, source_provider, output_path, request) -> RenderMetadata
render_project(project_path, output_path, request) -> RenderMetadata
```

`RenderRequest` starts at frame zero and accepts exactly one positive range:
`bars` or `seconds`. Its optional commands are ordered by nondecreasing frame;
frame zero and the range endpoint are valid. An empty command list produces
silence. Archive rendering validates the complete archive, decodes referenced
assets before creating output, and never rewrites the source project.

The output contract is stereo 32-bit floating-point WAV at the project sample
rate. The runtime uses a private quantization-free project snapshot so render
commands are exact even when the persisted session quantization is beat or bar.

### Exit criteria

- [x] Fixture projects export valid WAV files with the requested duration and
  channel count.
- [x] Repeated renders from the same project revision produce byte-identical
  output.
- [x] Missing, corrupt, unsupported, and metadata-mismatched assets fail before
  output replacement.
- [x] Existing output files remain unchanged on validation or render failure,
  and renderer temporary files are cleaned up.

### Verification

- Full Windows test suite: 54 passed on 2026-08-22.
- Ruff lint checks passed on 2026-08-22.
- Tests cover ranges, command timing/order, scenes, stops, silence, mixer
  behavior through the session engine, WAV metadata, deterministic output,
  resampling, clip-region conversion, archive validation, and output safety.

## Phase 4 — Windows audio backend

Phase 4 is implemented as a backend-only milestone. The reusable audio control
surface is available through `vibesound.audio`; CLI, HTTP API, and browser
integration remain in later phases. Automated verification is device-free, with
an opt-in Windows hardware smoke test for final machine-level validation.

### Components

1. [x] Define the thread-safe `AudioBackend` control interface and immutable
   device/configuration/snapshot types.
2. [x] Add `FakeAudioBackend` and preserve the Phase 3
   `OfflineRenderBackend` adapter for device-free tests and headless export.
3. [x] Add a preallocated single-producer/single-consumer ring buffer for
   fixed-size stereo float32 blocks.
4. [x] Add a PortAudio-backed implementation using `sounddevice` with a worker
   producer and a callback that performs only bounded buffer copying.
5. [x] Discover stereo-capable output devices and support OS-default or
   explicit index/name selection.
6. [x] Configure project sample rate, 512-frame default blocks, and a
   four-block default queue; reject real-time rate mismatches.
7. [x] Serialize play, pause, stop, reset, slot, scene, track-stop, and
   stop-all controls through the producer-owned session engine.
8. [x] Add clean start, pause, stop, reset, close, context-manager, and device
   release behavior.
9. [x] Surface stream-open, worker, callback, and underrun failures through
   typed errors and `AudioBackendSnapshot.last_error`.
10. [x] Add mocked PortAudio tests and an opt-in Windows hardware smoke test.

The audio callback must not perform file I/O, network operations, project saves,
or blocking operations. It consumes prepared blocks through the ring, emits
bounded silence on an underrun, records a typed fault, and lets a monitor thread
shut down the stream outside the callback.

### Exit criteria

- [x] A fixture project and manual test can play through a selected/default
  Windows output device.
- [x] The device is released when playback stops and when the process exits.
- [x] Device and callback failures are available through typed backend state;
  CLI/API presentation remains a later-phase responsibility.
- [x] Normal automated tests run without an audio device.

### Public backend contract

```text
PortAudioBackend(project, sources, config=AudioBackendConfig(...))
  start() / pause() / stop() / reset() / close()
  launch_slot(track_id, scene_id)
  launch_scene(scene_id)
  stop_track(track_id) / stop_all()
  snapshot() -> AudioBackendSnapshot

list_output_devices() -> tuple[AudioDeviceInfo, ...]
```

The PortAudio backend requires the project sample rate, outputs stereo float32,
and defaults to 512-frame blocks with four queued blocks. It uses the OS default
device unless an explicit device index or exact device name is configured. A
faulted backend is not automatically reopened; callers close it and construct a
new backend after correcting the device or runtime problem.

### Verification

- Device-free audio backend tests: 11 passed on 2026-08-22.
- The opt-in hardware check is marked `audio_device` and must be run manually
  on a Windows machine with a stereo output device:
  `uv run pytest -m audio_device -s`.
- CI runs `uv run pytest -m "not audio_device"` and retains the existing lint,
  CLI, renderer, and package-build checks.

### Current examples

- [x] Add numbered manually runnable examples `01` through `10` for project
  archives, generated music creation, deterministic session performance,
  offline arrangement rendering, the CLI, transaction safety, the API,
  backend comparison, PortAudio diagnostics/playback, and an agent producer
  workflow.
- [x] Reference every numbered example from `examples/README.md` with its
  command, artifact, and hardware prerequisite.
- [x] Keep generated example media under the ignored `examples/output/` path.
- [x] Run all nine device-free examples as subprocess smoke tests without
  opening a physical audio device; keep example `09` opt-in.

## Phase 5 — Application service and versioned API ✅ Complete

**Completed:** 2026-08-22

Phase 5 adds the shared application service and a versioned loopback API. One
service process owns one validated `.vibesound` archive, an injectable audio
backend, synchronous rendering, revisioned transactions, and bounded
WebSocket event subscriptions. The CLI and browser remain clients for later
phases.

### Components

1. [x] Add a shared `ApplicationService` with one-project lifecycle,
   serialized mutations, snapshots, close behavior, and backend injection.
2. [x] Add archive-backed playback source preparation that resamples assets
   while preserving live transport quantization.
3. [x] Implement whitelisted JSON-pointer `set` transactions for project name,
   transport values, track mixer values, scene names, and clip values.
4. [x] Implement observational previews, atomic commits, revision increments,
   stale-revision rejection, candidate validation, and runtime backend refresh.
5. [x] Add runtime transport and clip launch/stop operations backed by the
   Phase 4 audio contract.
6. [x] Add synchronous archive rendering with started, completed, and failed
   events.
7. [x] Add structured Pydantic API contracts and stable error envelopes.
8. [x] Add FastAPI routes under `/api/v1` and a loopback-default `uvicorn`
   server helper.
9. [x] Add bounded WebSocket event subscriptions that cannot block service
   mutations.
10. [x] Add the device-free API workflow example and smoke coverage.

### Transaction contract

```json
{
  "base_revision": 7,
  "operations": [
    {
      "op": "set",
      "path": "/tracks/<track-uuid>/mixer/gain_db",
      "value": -3.0
    }
  ]
}
```

Only whitelisted scalar paths may be changed. Entity creation/deletion, IDs,
asset references, clip slots, schema version, and sample rate remain outside
this phase. Preview never writes, increments a revision, refreshes audio, or
publishes events. A successful commit increments the revision once and writes
the archive through the existing atomic persistence layer. Transport and clip
controls are runtime-only.

### HTTP interface

```text
GET  /api/v1/projects/{project_id}
GET  /api/v1/projects/{project_id}/state
POST /api/v1/projects/{project_id}/transactions/preview
POST /api/v1/projects/{project_id}/transactions
POST /api/v1/projects/{project_id}/transport
POST /api/v1/projects/{project_id}/clips/{clip_id}/launch
POST /api/v1/projects/{project_id}/clips/{clip_id}/stop
POST /api/v1/projects/{project_id}/render
WS   /api/v1/projects/{project_id}/events
```

The API binds to `127.0.0.1` by default. Launch requests include `track_id`
and `scene_id`; render requests contain an output path, exactly one of `bars`
or `seconds`, and ordered exact-frame commands. Successful transaction,
control, and render responses use JSON-safe versions of the existing domain
contracts. Validation failures use structured `errors`; stale revisions return
HTTP 409.

### Event types

```text
project.changed
transport.changed
clip.launched
clip.stopped
render.started
render.completed
render.failed
audio.error
```

Events include the project ID, current revision, and operation payload. Clip
events expose the accepted quantized target frame. Exact audio-boundary event
streaming remains a later backend enhancement; the Phase 5 API publishes
accepted/scheduled control events.

### Verification

- Phase 5 service/API tests: 5 passed on 2026-08-22.
- All nine device-free numbered manual examples pass through subprocess smoke
  tests.
- Full device-free verification remains hardware-independent and uses the fake
  backend for API playback controls.
- The existing PortAudio hardware smoke test remains opt-in under the
  `audio_device` marker.

### Exit criteria

- [x] API clients can inspect and mutate one project.
- [x] Dry-run requests never change persisted or live state.
- [x] Stale transactions are rejected predictably.
- [x] WebSocket clients receive state changes.
- [x] Runtime controls and rendering share the application service.
- [x] CLI and future browser clients have a stable versioned service boundary.


## Phase 5.5 — Product alignment, authoring completeness, and application hardening

**Status: implemented.** The stable contracts and operational limits are
summarized in [PHASE_5_5.md](PHASE_5_5.md).

Phase 5.5 is the mandatory stabilization milestone between the completed
application service/API and the general CLI surface. It keeps VibeSound focused
as a Python-first DAW for musicians and coding agents, closes the incomplete
authoring loop, and fixes persistence, runtime, security, operability, and
delivery risks before additional clients depend on the current contracts.

The milestone may make significant internal architectural changes while the
project is young. Existing portable project archives must remain usable through
transparent migration. Public contracts introduced here become the stable
foundation for the CLI and browser phases.

### Fixed decisions

- **Product identity:** VibeSound remains a DAW for musicians and coding agents.
  Audio fingerprinting, YouTube extraction, catalogue search, and track
  identification are outside this product roadmap.
- **Target scale:** ordinary projects with up to roughly 50 tracks and several
  gigabytes of audio must remain responsive without loading or rewriting the
  complete project for routine edits.
- **Storage:** retain the portable .vibesound archive and add an efficient
  working-project directory representation. Opening an existing archive must
  transparently create or migrate a compatible working representation; portable
  archive export remains explicit and deterministic.
- **Compatibility:** existing schema-version-1 archives must open without manual
  repair. Migrations must be tested and must preserve IDs, audio bytes, metadata,
  revision history, and audible behavior.
- **Mutation model:** expose typed domain operations and retain UUIDs as canonical
  identifiers. Clients may resolve unique human-readable names, but persisted
  operations and responses use UUIDs.
- **Ownership:** one application-service process owns a writable project. Other
  processes use the service API. Direct writers require an exclusive project
  lock.
- **Network boundary:** local loopback only in the POC. Reject non-loopback
  binding and WebSocket origins not served by VibeSound.
- **Exports:** API renders use project-local exports by default. Additional
  destinations require an explicit configured allowlist.
- **Runtime edits:** mixer changes apply without backend recreation. Other edits
  preserve transport and active clips whenever safe; unavoidable resets are
  previewed and reported explicitly.
- **Rendering:** render work runs as revision-bound background jobs with status,
  progress, cancellation, and bounded event publication.
- **Audio availability:** inspection, editing, validation, and offline rendering
  remain available without a physical output device. Device discovery and
  selection are explicit, and transient underruns are recoverable.
- **Deletion safety:** destructive structural operations fail when dependants
  exist unless the caller explicitly requests a previewed cascade.
- **Engineering gate:** type checking, coverage, package installation,
  concurrency, security, contract, realistic-scale, Windows, and Linux
  device-free checks are part of this phase.

### Architecture boundaries

Split the current application responsibilities behind explicit interfaces:

- ProjectRepository owns working-project persistence, portable archive
  import/export, migrations, locking, and external-change detection.
- ProjectCommandService validates and applies typed, revisioned project
  operations.
- AudioRuntimeCoordinator owns playback state, device configuration, runtime
  mixer updates, actual engine events, latency, and recoverable faults.
- RenderJobService owns immutable render snapshots, job lifecycle, progress,
  cancellation, and output policy.
- ApplicationService composes these boundaries and exposes stable client
  contracts without decoding audio or rewriting storage for every request.

Metadata-only previews and commits must not decode audio, rebuild an audio
backend, or rewrite embedded asset bytes. Runtime validation may prepare only
the assets affected by an operation.

### Typed authoring operations

Add previewable and atomically committed operations for:

1. Create, rename, reorder, and delete tracks.
2. Create, rename, reorder, and delete scenes.
3. Import, inspect, and delete audio assets.
4. Create, update, duplicate, and delete audio clips.
5. Assign, replace, clear, and inspect track/scene clip slots.
6. Update transport and mixer values.
7. Apply explicit cascade deletion after returning its complete impact in a
   preview.
8. Resolve a unique entity name to its canonical UUID.
9. Apply multiple operations as one revisioned transaction.
10. Return created IDs, changed IDs, deleted IDs, changed paths, reset impact,
    and validation issues in stable JSON contracts.

Name resolution must reject missing and ambiguous matches. Operations must be
idempotent where a safe idempotency key is supplied, so an agent can retry a
request without duplicating entities.

### Project validation and storage

1. Separate archive-integrity, schema, project-reference, playback-readiness,
   and device-compatibility validation results.
2. Ensure a project reported as playback-ready can initialize the runtime with
   every referenced asset.
3. Validate clip source regions, supported channel layouts, decodability,
   ordering, and runtime sample-rate preparation.
4. Define bounded ZIP member count, manifest size, expanded asset size, total
   expanded size, and compression-ratio limits.
5. Stream asset hashing, copying, archive import, and archive export rather than
   materializing complete projects in memory.
6. Avoid recompressing unchanged audio for scalar or structural metadata edits.
7. Add an exclusive writer lock and a persisted source fingerprint.
8. Detect external changes, pause writes, publish a project.external_change
   event, and require explicit reload or conflict resolution. Never silently
   overwrite or automatically merge an externally changed project.
9. Keep portable archive output deterministic and atomic.
10. Benchmark the working format and portable export with representative
    projects up to the target scale.

The exact working-directory suffix and cache placement must be recorded in a
short architecture decision record before implementation. The representation
must be inspectable, recoverable after interruption, and safe to remove without
damaging the last portable archive.

### Runtime behavior

1. Apply gain, pan, mute, and solo changes directly to runtime-safe mixer state
   without reconstructing the backend.
2. Classify project operations by runtime impact: no refresh, incremental
   refresh, transport-preserving rebuild, or required reset.
3. Include runtime impact in transaction previews and commit responses.
4. Preserve device selection, transport position, mode, active clips, and
   pending launches across safe changes.
5. Reject or explicitly reset operations that cannot preserve valid runtime
   state.
6. Publish distinct clip.scheduled, clip.launched, clip.stopped, and
   clip.completed events from actual backend/engine state.
7. Report both render-head position and estimated audible position, including
   queued output latency.
8. Expose output-device discovery, selection, diagnostics, and controlled
   backend restart through the service.
9. Fall back to a device-free editing backend when no usable output device is
   available.
10. Treat isolated underruns as recoverable diagnostics. Fault playback only
    after a documented threshold or an unrecoverable callback/worker error.
11. Replace preview-quality linear sample-rate conversion for playback with a
    quality-defined, anti-aliased implementation behind the existing resampling
    boundary.
12. Add realistic producer-load and shutdown tests; verify that background
    threads terminate or return a structured failure.

### Render jobs and output policy

1. Capture an immutable project revision snapshot when a job is accepted.
2. Return a stable job ID immediately.
3. Expose queued, running, completed, failed, and cancelled states.
4. Publish bounded progress and terminal events without holding the main
   application lock.
5. Allow cancellation between render blocks and guarantee temporary-file
   cleanup.
6. Keep transport, inspection, WebSocket delivery, and safe project operations
   responsive during a render.
7. Restrict default outputs to the project export root and resolve all paths
   before writing.
8. Permit extra output roots only through explicit trusted configuration.
9. Record revision, request, output hash, timestamps, and failure details in
   job metadata.
10. Define retention and cleanup behavior for completed jobs and temporary
    artifacts.

### API hardening and discoverability

1. Add health, readiness, application-version, API-version, capabilities, and
   schema-discovery endpoints.
2. Add structural authoring, asset-import, device, runtime-recovery, and render
   job endpoints using the shared typed contracts.
3. Keep one stable error envelope for validation, conflict, I/O, runtime,
   security, and cancellation failures.
4. Enforce request-body, imported-asset, transaction-operation, and subscriber
   queue limits.
5. Reject non-loopback serving during the POC.
6. Validate HTTP and WebSocket origins against the VibeSound-served origin.
7. Never accept arbitrary filesystem output paths without an allowlisted root.
8. Distinguish command acceptance from actual runtime state transitions.
9. Add idempotency support for retriable mutating requests.
10. Publish and contract-test the generated OpenAPI schema.

### Plug-and-play acceptance flow

Provide a generated demo project using redistributable synthetic audio. An
installed package must offer one minimal acceptance launcher that creates or
opens the demo and starts the local service with one command. This launcher is
the exception needed to prove installation and operability; the complete CLI
surface remains Phase 6.

The acceptance flow must:

1. Install the built wheel into a clean Python 3.12 environment.
2. Create or open the generated demo in one command.
3. Start the loopback service without requiring an audio device.
4. Inspect capabilities and project state.
5. Import audio and create tracks, scenes, clips, and slot assignments only
   through public contracts.
6. Preview and commit a multi-operation agent transaction.
7. Apply mixer edits without resetting transport.
8. Start a background render, observe progress, and obtain its output hash.
9. Export a deterministic portable .vibesound archive.
10. Close, reopen, and verify IDs, revisions, assets, and audible output.

### Verification

Add all of the following gates:

- Static type checking for the package and typed public tests.
- Coverage reporting with a documented minimum threshold.
- Wheel and source-archive build, clean installation, and installed-command
  smoke tests.
- Windows and Linux device-free CI.
- API/OpenAPI contract snapshots and backward-compatibility checks.
- Concurrent request, exclusive lock, stale revision, and external-change tests.
- ZIP limits, traversal, symlink, decompression, export-root, host, and origin
  security tests.
- Render responsiveness, progress, cancellation, and cleanup tests.
- Runtime state-preservation and explicit-reset tests.
- Device absence, selection, recoverable underrun, fault, and restart tests.
- Realistic-duration audio and bounded representative large-project benchmarks.
- Transparent migration tests for every existing schema-version-1 fixture.
- A public-contract end-to-end test that does not mutate Pydantic entity lists
  or depend on private example helpers.

Large-project tests may use sparse or generated assets and bounded benchmark
thresholds in CI, with full multi-gigabyte validation available as an opt-in
local test.

### Exit criteria

- A public client can create, edit, play, render, export, and reopen a project
  without direct model mutation.
- Existing portable projects migrate transparently and preserve content.
- Routine metadata and mixer edits do not decode or rewrite unchanged audio.
- Concurrent or external writers cannot silently overwrite project state.
- A validated playback-ready project opens successfully in device-free mode.
- Playback remains usable after transient underruns and exposes device recovery.
- Safe edits preserve runtime state; required resets are previewed and explicit.
- Events distinguish scheduled commands from actual engine transitions.
- Rendering is asynchronous, cancellable, revision-bound, and non-blocking.
- Loopback, origin, output-path, archive-resource, and request limits are tested.
- The built wheel passes the complete one-command demo acceptance flow on a clean
  environment.
- Phase 6 can implement CLI commands entirely as a client of these stable
  contracts.

### Non-goals

- The complete general CLI command set, which remains Phase 6.
- The browser session UI, which remains Phase 7.
- Standalone Windows installers, which remain a release milestone.
- Remote access or collaboration.
- VST3, MIDI, recording, arrangement editing, and automation.
- Audio fingerprinting, YouTube extraction, catalogue search, or track
  identification.


## Phase 6 — CLI surface

### Example maintenance gate

- [x] Extend the CLI workflow example for every released command, including
  transport, clip launch/stop, transaction preview/commit, render, and serve;
  keep JSON output and prerequisites current.

### Commands

```text
vibesound project init PATH
vibesound project show|validate PROJECT [--portable]
vibesound project state|export|detach-source PROJECT
vibesound project migrate ARCHIVE
vibesound server status|capabilities|schemas PROJECT
vibesound entity list|resolve PROJECT TYPE
vibesound audio import PROJECT FILE
vibesound audio devices|restart PROJECT
vibesound session launch|stop PROJECT
vibesound transport play|pause|stop|reset PROJECT
vibesound transaction preview PROJECT OPS_FILE
vibesound transaction commit PROJECT OPS_FILE
vibesound render PROJECT (--bars N | --seconds N)
vibesound job list|show|wait|cancel PROJECT
vibesound events watch PROJECT
vibesound serve PROJECT
```

### CLI rules

- [x] Human-readable output by default.
- [x] Versioned `--json` envelopes for finite machine-readable output and JSONL
  for event streaming.
- [x] Stable non-zero exit codes for usage, validation, conflict, I/O, service,
  audio, job, internal, and interruption failures.
- [x] Mutating commands support server-backed preview or `--dry-run`.
- [x] Service commands call the shared API and verify local/service project IDs.
- [x] Service discovery uses an explicit loopback URL and never starts a hidden
  daemon.
- [x] Entity selectors accept UUIDs or unique exact case-insensitive names.
- [x] Render and export wait by default and support `--no-wait`.

The complete command grammar and output contract are documented in
[`PHASE_6.md`](PHASE_6.md).

### Exit criteria

- [x] An agent can complete the POC workflow without opening the browser.
- [x] JSON output is versioned and stable enough for agent tooling.
- [x] Every mutating command has a safe preview path.

## Phase 7 — Browser session UI

### Example maintenance gate

- [x] Add/update a manually runnable browser example or local launch workflow,
  document its URL and prerequisites, and keep it separate from device-free
  command-line examples.

### Components

1. [x] Serve static HTML, CSS, and JavaScript from the Python application.
2. [x] Add a project header and revision indicator.
3. [x] Add transport controls.
4. [x] Add tempo display.
5. [x] Add a session grid.
6. [x] Add track and scene labels.
7. [x] Add clip launch buttons.
8. [x] Add active-clip state.
9. [x] Add gain and pan controls.
10. [x] Add mute and solo controls.
11. [x] Add render control.
12. [x] Add validation and error display.
13. [x] Subscribe to WebSocket events.
14. [x] Resolve stale revision errors without silently overwriting state.

The shipped UI, synchronization contract, launch commands, security boundary,
and Chromium gate are documented in [`PHASE_7.md`](PHASE_7.md).

### Exit criteria

- [x] A user can launch and stop clips from the UI.
- [x] UI mix changes reach the engine.
- [x] CLI changes appear in the browser without refresh.
- [x] Browser errors remain understandable and recoverable.

## Phase 8 — Reproducible POC release

**Status: implemented.** The canonical fixture, executable workflow, clean-wheel
Windows gate, and artifact contract are documented in
[`PHASE_8.md`](PHASE_8.md).

### Example maintenance gate

- [x] Promote the POC fixture and acceptance flow into a repeatable example,
  including the browser, CLI, transaction, render, and reopen steps.

Create a fixture project with:

- [x] Two tracks.
- [x] Two scenes.
- [x] Several short audio clips.
- [x] Known tempo and quantization.
- [x] Different gain and pan values.
- [x] At least one muted track.

The acceptance flow is:

1. [x] Initialize or load the fixture project.
2. [x] Open the browser UI.
3. [x] Launch clips from the UI.
4. [x] Launch another clip through the CLI.
5. [x] Change gain and mute state through a transaction.
6. [x] Preview an invalid transaction and verify there is no state change.
7. [x] Export a WAV.
8. [x] Close and reopen the project.
9. [x] Verify the project revision and content.
10. [x] Run the complete automated test suite.

The POC is complete: CI runs this flow against the exact installed wheel on a
clean Windows environment without third-party plugins.

## Phase 9 — VST3 plugin worker

### Example maintenance gate

- [ ] Add an opt-in plugin example for discovery, parameter control, state
  round-trip, and failure recovery; document the user-installed plugin
  prerequisite and keep it out of the normal smoke suite.

Begin only after the POC acceptance flow is stable.

### Components

1. Configure user plugin search paths.
2. Add an explicit plugin allowlist.
3. Discover plugins in a separate process.
4. Store plugin metadata in a registry.
5. Load one known compatible VST3 effect.
6. Enumerate parameters.
7. Read and write parameters.
8. Add bypass control.
9. Save and restore plugin state.
10. Process audio offline through the worker.
11. Add a worker request/response protocol.
12. Add worker timeouts.
13. Detect worker crashes.
14. Automatically bypass a failed plugin.
15. Publish plugin error events.
16. Restart the worker safely.
17. Attempt real-time integration only after offline processing is stable.

Keep the plugin implementation behind this interface:

```text
list_plugins()
load_plugin(plugin_id)
get_plugin_parameters(plugin_id)
set_plugin_parameter(plugin_id, parameter_id, value)
set_plugin_bypass(plugin_id, enabled)
save_plugin_state(plugin_id)
restore_plugin_state(plugin_id, state)
unload_plugin(plugin_id)
```

Third-party plugins are user-installed dependencies. VibeSound must not ship
plugin binaries or bypass plugin licensing.

## Phase 10 — Features after the POC

### Example maintenance gate

- [ ] For each post-POC feature, add or update the smallest runnable example
  that demonstrates the new public behavior and record any environment
  requirements in `examples/README.md`.

Implement each item as a separate milestone:

1. MIDI clip data model.
2. MIDI note scheduling.
3. Instrument plugin support.
4. Linear arrangement timeline.
5. Clip move, trim, split, and duplicate operations.
6. Undo and redo through transaction history.
7. Automation lanes.
8. Send/return routing.
9. Master bus processing.
10. Audio input recording.
11. Latency measurement and compensation.
12. Plugin preset browsing.
13. Project snapshots and branching.
14. Agent multi-step plans and transaction batches.
15. Windows packaging.
16. Optional authenticated remote API.

## Public data contracts

### Failed transaction

```json
{
  "ok": false,
  "base_revision": 7,
  "current_revision": 8,
  "errors": [
    {
      "code": "stale_revision",
      "path": "",
      "message": "Project changed after the transaction was created."
    }
  ]
}
```

### Successful transaction

```json
{
  "ok": true,
  "before_revision": 7,
  "after_revision": 8,
  "changed_paths": [
    "/tracks/drums/mixer/gain_db"
  ]
}
```

These contracts must be versioned before they are exposed to coding agents.

## Test plan

### Unit tests

- Project model validation.
- Deterministic serialization.
- Asset path safety.
- Atomic saves.
- Schema migrations.
- Transport state transitions.
- Quantization.
- Gain, pan, mute, and solo.
- Deterministic rendering.

### Integration tests

- Project creation through reload.
- CLI JSON output.
- HTTP API contract.
- Dry-run behavior.
- Stale revision rejection.
- WebSocket event publication.
- Render failures and cleanup.

### Environment-specific tests

- Windows audio-device smoke test.
- Browser interaction smoke test.
- VST worker load and parameter round-trip.
- VST worker crash isolation and restart.

Tests requiring an audio device or third-party plugin must be marked separately
and must not block the normal test suite.

## Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Real-time audio timing is unreliable in ordinary Python code | Keep the engine deterministic, isolate the callback, and test offline first. |
| A VST plugin crashes the host | Run plugin discovery and processing in a worker with watchdog and bypass behavior. |
| Agents overwrite concurrent user edits | Require base revisions and atomic transaction commits. |
| Project files become opaque or hard to migrate | Use deterministic JSON, explicit schema versions, and migrations from the beginning. |
| UI and CLI behavior diverge | Make both clients call the same application service. |
| Audio-device tests are flaky in CI | Keep hardware tests separate from deterministic tests. |

## Definition of done for this bootstrap

- The repository is checked out locally.
- `README.md` explains the product and POC boundary.
- `docs/IMPLEMENTATION_PLAN.md` contains the incremental implementation
  sequence.
- The Python package can be installed with `uv`.
- The minimal CLI exposes help and version commands.
- The smoke test passes.
- The bootstrap commit is pushed to the private GitHub repository.
