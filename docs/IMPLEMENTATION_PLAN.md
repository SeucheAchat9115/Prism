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

- [x] Add manually runnable examples for project archives, the current CLI,
  deterministic engine control, offline rendering, the fake backend, and
  PortAudio playback.
- [x] Keep generated example media under the ignored `examples/output/` path.
- [x] Run all device-free examples as subprocess smoke tests without opening a
  physical audio device.

## Phase 5 — Application service and versioned API

### Example maintenance gate

- [ ] Add/update a device-free example for service snapshots, transaction
  preview/commit, revision conflicts, and API events; update the example index
  and smoke coverage.

### Components

1. Add a shared application service independent of CLI and browser code.
2. Implement `load_project` and `get_snapshot`.
3. Implement transaction validation.
4. Implement transaction preview.
5. Implement atomic transaction commit.
6. Add revision conflict detection.
7. Add transport operations.
8. Add clip-launch operations.
9. Add render operations.
10. Add FastAPI HTTP routes.
11. Add WebSocket event publication.
12. Add structured API errors.
13. Bind the development server to loopback only.

### Transaction envelope

```json
{
  "base_revision": 7,
  "operations": [
    {
      "op": "set",
      "path": "/tracks/drums/mixer/gain_db",
      "value": -3.0
    }
  ]
}
```

### Required HTTP interface

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

### Required event types

```text
project.changed
transport.changed
clip.launched
clip.stopped
render.started
render.completed
audio.error
plugin.error
```

### Transaction invariants

- Validate every operation before mutation.
- Reject unknown paths and invalid values.
- Reject stale `base_revision` values.
- Never partially apply a failed transaction.
- Increment the revision once per successful transaction.
- Return changed paths and before/after revisions.
- Make dry runs observational only.

### Exit criteria

- API clients can inspect and mutate a project.
- Dry-run requests never change persisted or live state.
- Stale transactions are rejected predictably.
- WebSocket clients receive state changes.
- CLI and API produce equivalent service results.

## Phase 6 — CLI surface

### Example maintenance gate

- [ ] Extend the CLI workflow example for every released command, including
  transport, clip launch/stop, transaction preview/commit, render, and serve;
  keep JSON output and prerequisites current.

### Commands

```text
vibesound project init PATH
vibesound project validate PATH
vibesound project show PATH
vibesound audio import PROJECT FILE --track TRACK_ID
vibesound session launch PROJECT --track TRACK_ID --scene SCENE_ID
vibesound session stop PROJECT --track TRACK_ID
vibesound transport play PROJECT
vibesound transport stop PROJECT
vibesound transaction preview PROJECT OPS_FILE
vibesound transaction commit PROJECT OPS_FILE
vibesound render PROJECT --output OUTPUT_FILE
vibesound serve PROJECT
```

### CLI rules

- Human-readable output by default.
- `--json` for machine-readable output.
- Stable non-zero exit codes for validation, revision, I/O, and render errors.
- Mutating commands support preview or `--dry-run` where applicable.
- Commands call the shared application service instead of editing JSON directly.

### Exit criteria

- An agent can complete the POC workflow without opening the browser.
- JSON output is stable enough for agent tooling.
- Every mutating command has a safe preview path.

## Phase 7 — Browser session UI

### Example maintenance gate

- [ ] Add/update a manually runnable browser example or local launch workflow,
  document its URL and prerequisites, and keep it separate from device-free
  command-line examples.

### Components

1. Serve static HTML, CSS, and JavaScript from the Python application.
2. Add a project header and revision indicator.
3. Add transport controls.
4. Add tempo display.
5. Add a session grid.
6. Add track and scene labels.
7. Add clip launch buttons.
8. Add active-clip state.
9. Add gain and pan controls.
10. Add mute and solo controls.
11. Add render control.
12. Add validation and error display.
13. Subscribe to WebSocket events.
14. Resolve stale revision errors without silently overwriting state.

### Exit criteria

- A user can launch and stop clips from the UI.
- UI mix changes reach the engine.
- CLI changes appear in the browser without refresh.
- Browser errors remain understandable and recoverable.

## Phase 8 — Reproducible POC release

### Example maintenance gate

- [ ] Promote the POC fixture and acceptance flow into a repeatable example,
  including the browser, CLI, transaction, render, and reopen steps.

Create a fixture project with:

- Two tracks.
- Two scenes.
- Several short audio clips.
- Known tempo and quantization.
- Different gain and pan values.
- At least one muted track.

The acceptance flow is:

1. Initialize or load the fixture project.
2. Open the browser UI.
3. Launch clips from the UI.
4. Launch another clip through the CLI.
5. Change gain and mute state through a transaction.
6. Preview an invalid transaction and verify there is no state change.
7. Export a WAV.
8. Close and reopen the project.
9. Verify the project revision and content.
10. Run the complete automated test suite.

The POC is complete only when this flow works on a clean Windows environment
without third-party plugins.

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
