# Prism

Prism is a Python-first digital audio workstation designed for two kinds of
users: musicians working in a browser-based session view and coding agents that
need to inspect, change, render, and validate music projects programmatically.

The long-term goal is an Ableton-like workflow with a local web application, a
command-line interface, a stable machine-readable API, and controllable VST3
plugins. The application code, project model, CLI, API, and orchestration layer
will be Python. Native audio and plugin libraries are allowed behind Python
interfaces where low-latency audio requires them.

## Why Prism?

Music production is full of structured decisions: which clips are active, how
tracks are mixed, when a scene launches, which effects are enabled, and which
render should be kept. Prism makes those decisions explicit and versionable
so that a coding agent can help with production without having to drive pixels
or guess at undocumented application state.

The intended control flow is:

```text
Browser UI ─┐
            ├─ Local Prism service ─ Project model ─ Audio engine ─ Audio device
CLI ────────┘                         └─ Isolated plugin worker
Coding agent ─ Versioned local API
```

The browser and CLI are clients. The Python application service owns project
validation, state changes, transport, rendering, and event publication.

## Current status

This repository contains the completed Phase 8 proof of concept: working-project
storage, typed authoring, deterministic rendering, device-free runtime fallback,
a hardened local v1 API, the complete service-backed CLI, and the packaged
browser session are now exercised together against the exact built wheel on a
clean Windows environment.

The project documentation is organized as follows:

- [Implementation plan](docs/IMPLEMENTATION_PLAN.md) — the component-by-component
  roadmap and acceptance criteria.
- [Deployment guide](docs/DEPLOYMENT.md) — local builds, command-line
  installation, releases, CD automation, and future standalone packages.
- [Phase 5.5 contracts](docs/PHASE_5_5.md) — working storage, typed operations,
  jobs, runtime behavior, security limits, and acceptance commands.
- [Phase 6 CLI](docs/PHASE_6.md) — commands, service lifecycle, JSON envelopes,
  dry runs, selectors, job waiting, and stable exit codes.
- [Phase 7 browser session](docs/PHASE_7.md) — launch workflow, controls,
  synchronization, conflict handling, local security, and browser tests.
- [Phase 8 reproducible POC](docs/PHASE_8.md) — canonical fixture, full
  browser/CLI acceptance flow, artifacts, and clean-wheel Windows gate.
- [Manual examples](examples/README.md) — runnable examples for the current
  persistence, engine, rendering, CLI, and audio-backend features.

## Agent guidance

Prism includes a repository-wide [agent guide](AGENTS.md) and discoverable
skills under [`.agents/skills/`](.agents/skills/). Together they teach a coding
agent the repository architecture, product invariants, validation workflow, and
which Prism interface to use for a task:

- `$prism-repository-development` for source, tests, documentation, and release
  work inside this repository.
- `$prism-project-authoring` for safe project inspection and transactional edits.
- `$prism-session-control` for transport, live sessions, audio, events, and the
  browser UI.
- `$prism-render-export` for audio import, render jobs, portable export, and
  artifact verification.
- `$prism-api-integration` for typed Python clients, raw HTTP/WebSocket clients,
  errors, retries, and agent-tool wrappers.

Compatible agents discover these skills from the repository automatically.
They can also be invoked explicitly, for example: “Use
`$prism-project-authoring` to add a track and scene, preview the transaction,
and commit it.” The root guide routes cross-cutting tasks to the smallest useful
combination of skills.

The Phase 3 renderer is available through `prism.rendering.render()` for
loaded projects with injected sources and `prism.rendering.render_project()`
for self-contained `.prism` archives. Both produce deterministic stereo
float32 WAV files without requiring an audio device.

The `prism.audio` package provides fake, offline, and PortAudio-backed
backends. Device-free tests run by default; the real-device smoke test is
opt-in with `uv run pytest -m audio_device -s` on Windows.

The [`examples/`](examples/README.md) folder mirrors this current feature
boundary with twelve numbered generated-audio scripts. Nine examples run
without hardware; PortAudio diagnostics, the blocking browser launcher, and the
complete Playwright-driven POC are explicitly opt-in.

The API is available through `prism.api.create_app()` for embedding,
`prism.api.run_server(PROJECT)` for a loopback-only server, and
`prism.api.PrismClient` for typed callers. The CLI starts a foreground
service explicitly; it never creates an invisible daemon:

```text
prism serve demo.prism-work
```

Add `--open` to request the Phase 7 session in the system browser after the
service has bound, or open the printed URL manually:

```text
prism demo demo.prism-work --open
prism serve demo.prism-work --open
```

Service-backed commands default to `http://127.0.0.1:8765`. Override it with
`--url` or `PRISM_URL`; only loopback targets are accepted. The named local
project must match the project ID reported by readiness before a command runs.

## Completed POC

The first POC proves the project and control loop before taking on plugin-hosting
complexity. It supports:

- Audio clip import from WAV/AIFF assets.
- Tracks and scenes in a session-style view.
- Tempo, transport, and quantized clip launching.
- Track volume, pan, mute, and solo.
- Local Windows playback.
- Headless WAV export.
- Self-contained `.prism` ZIP projects with a structured JSON manifest and
  embedded audio assets.
- A CLI for inspection and mutation.
- A versioned local HTTP/WebSocket API for coding agents.
- A lightweight browser UI served by the Python process.

The POC does not include VST hosting, MIDI instruments, recording, a linear
arrangement timeline, automation lanes, collaboration, or remote access.

## Agent CLI workflow

The CLI and API expose the same application service. Start it in one terminal:

```text
prism project init demo.prism-work
prism serve demo.prism-work
```

Then use another terminal or agent process:

```text
prism audio import demo.prism-work drums.wav --json
prism transaction preview demo.prism-work operations.json --json
prism transaction commit demo.prism-work operations.json --json
prism session launch demo.prism-work --track Drums --scene Verse --json
prism render demo.prism-work --bars 8 --output demo.wav --json
prism project export demo.prism-work --output demo.prism --json
```

Transactions accept either a complete request object or a bare operations array.
Every mutation is revision-checked and has a server-backed preview or `--dry-run`
path. JSON commands use a versioned envelope; invalid or stale requests leave the
project unchanged and return stable, documented process exit codes.

## Project format

Portable projects are self-contained ZIP archives with a custom `.prism`
extension. Routine service edits occur in an adjacent `.prism-work/`
directory and portable ZIP creation is explicit:

```text
demo.prism
├── project.json
└── assets/
    └── audio/
        └── <asset-uuid>.wav
```

The archive contains versioned project metadata, stable UUIDs, tracks, scenes,
clip slots, clips, transport settings, mixer state, and asset metadata in
`project.json`. Imported audio is copied into `assets/audio/`, keeping each
project portable and safe for agent-driven workflows.

Archive writes are deterministic and atomic. Prism validates member paths,
rejects traversal and symlink entries, preserves imported audio bytes, and only
rewrites an existing project through an explicit save or migration operation.
The manifest remains inspectable with standard ZIP tools while the custom
extension makes project files recognizable to Prism.

The working representation keeps ordinary `project.json`, immutable assets,
revision history, project-local exports, and internal lock/staging/cache/job
state. Removing it does not damage the last portable archive.

## Architecture principles

- Keep the domain model independent of the browser and audio device.
- Make the CLI and HTTP API call the same application service.
- Keep real-time audio callbacks small and non-blocking.
- Render offline through the same scheduling and mixing rules used by playback.
- Validate and atomically commit project mutations.
- Bind the initial API to `127.0.0.1` only.
- Keep schema versions and migration code from the first project format onward.
- Run VST3 plugins outside the main application process.
- Treat third-party plugin binaries as user-installed dependencies rather than
  something Prism redistributes.

## Technology direction

The initial implementation targets Python 3.12 on Windows and uses `uv` for
environment management. The planned building blocks are:

- Pydantic for validated project and transaction models.
- NumPy for audio buffers and deterministic rendering.
- `sounddevice`/PortAudio for the first device backend.
- FastAPI for the local HTTP and WebSocket API.
- Typer for the CLI.
- HTML, CSS, and vanilla JavaScript served as static assets, with no Node build
  requirement.
- Pedalboard as the first VST3 hosting candidate after the POC, behind an
  isolated worker interface.

Real-time audio and VST hosting rely on native components behind Python APIs;
“Python-first” describes the product and orchestration boundary, not a promise
that every low-level audio operation will be implemented in pure Python.

## Roadmap

```text
Repository foundation
  → Project schema and persistence
  → Deterministic session engine
  → Offline renderer
  → Windows audio playback
  → CLI and versioned API
  → Product and application hardening
  → Complete CLI surface
  → Browser session UI
  → Reproducible POC
  → Isolated VST3 worker
  → MIDI clips and instruments
  → Arrangement timeline and editing
  → Automation, routing, and recording
  → Packaging and advanced agent workflows
```

## Development commands

Once the environment is installed:

```powershell
uv sync --extra dev
uv run pytest -m "not audio_device and not browser"
uv run pytest -m browser --browser chromium
uv run ruff check .
uv run mypy src/prism
uv run python -m prism --help
uv run prism version
```

The implementation is intentionally incremental. Each phase in the
[implementation plan](docs/IMPLEMENTATION_PLAN.md) has a small component
boundary, tests, and an exit criterion before the next layer is added. See the
[deployment guide](docs/DEPLOYMENT.md) for how those builds become installable
command-line releases.
