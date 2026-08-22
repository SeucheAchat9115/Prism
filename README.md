# VibeSound

VibeSound is a Python-first digital audio workstation designed for two kinds of
users: musicians working in a browser-based session view and coding agents that
need to inspect, change, render, and validate music projects programmatically.

The long-term goal is an Ableton-like workflow with a local web application, a
command-line interface, a stable machine-readable API, and controllable VST3
plugins. The application code, project model, CLI, API, and orchestration layer
will be Python. Native audio and plugin libraries are allowed behind Python
interfaces where low-latency audio requires them.

## Why VibeSound?

Music production is full of structured decisions: which clips are active, how
tracks are mixed, when a scene launches, which effects are enabled, and which
render should be kept. VibeSound makes those decisions explicit and versionable
so that a coding agent can help with production without having to drive pixels
or guess at undocumented application state.

The intended control flow is:

```text
Browser UI ─┐
            ├─ Local VibeSound service ─ Project model ─ Audio engine ─ Audio device
CLI ────────┘                         └─ Isolated plugin worker
Coding agent ─ Versioned local API
```

The browser and CLI are clients. The Python application service owns project
validation, state changes, transport, rendering, and event publication.

## Current status

This repository contains the Python package foundation, project persistence, a
deterministic in-memory session engine, an archive-backed offline renderer, and
the Windows-first audio backend. The next implementation milestone is the
application service and versioned API; the staged roadmap and deployment
guidance are linked below.

The project documentation is organized as follows:

- [Implementation plan](docs/IMPLEMENTATION_PLAN.md) — the component-by-component
  roadmap and acceptance criteria.
- [Deployment guide](docs/DEPLOYMENT.md) — local builds, command-line
  installation, releases, CD automation, and future standalone packages.
- [Manual examples](examples/README.md) — runnable examples for the current
  persistence, engine, rendering, CLI, and audio-backend features.

The Phase 3 renderer is available through `vibesound.rendering.render()` for
loaded projects with injected sources and `vibesound.rendering.render_project()`
for self-contained `.vibesound` archives. Both produce deterministic stereo
float32 WAV files without requiring an audio device.

The `vibesound.audio` package provides fake, offline, and PortAudio-backed
backends. Device-free tests run by default; the real-device smoke test is
opt-in with `uv run pytest -m audio_device -s` on Windows.

The [`examples/`](examples/README.md) folder mirrors this current feature
boundary with generated-audio scripts. Five examples run without hardware; the
PortAudio playback example is explicitly opt-in.

## POC target

The first POC deliberately proves the project and control loop before taking on
plugin-hosting complexity. It will support:

- Audio clip import from WAV/AIFF assets.
- Tracks and scenes in a session-style view.
- Tempo, transport, and quantized clip launching.
- Track volume, pan, mute, and solo.
- Local Windows playback.
- Headless WAV export.
- Self-contained `.vibesound` ZIP projects with a structured JSON manifest and
  embedded audio assets.
- A CLI for inspection and mutation.
- A versioned local HTTP/WebSocket API for coding agents.
- A lightweight browser UI served by the Python process.

The POC will not include VST hosting, MIDI instruments, recording, a linear
arrangement timeline, automation lanes, collaboration, or remote access.

## Planned agent workflow

The CLI and API will expose the same application service. A typical future
workflow will look like this:

```text
vibesound project init demo.vibesound
vibesound asset import demo.vibesound drums.wav --json
vibesound project validate demo.vibesound --json
vibesound transaction preview demo.vibesound operations.json
vibesound transaction commit demo.vibesound operations.json
vibesound render demo.vibesound --output exports/demo.wav
```

Agent mutations will be structured transactions. Every transaction will include
the project revision it was based on, will be validated before application, and
will support a dry-run preview. Invalid or stale transactions will leave the
project unchanged.

## Project format

Projects are self-contained ZIP archives with a custom `.vibesound` extension:

```text
demo.vibesound
├── project.json
└── assets/
    └── audio/
        └── <asset-uuid>.wav
```

The archive contains versioned project metadata, stable UUIDs, tracks, scenes,
clip slots, clips, transport settings, mixer state, and asset metadata in
`project.json`. Imported audio is copied into `assets/audio/`, keeping each
project portable and safe for agent-driven workflows.

Archive writes are deterministic and atomic. VibeSound validates member paths,
rejects traversal and symlink entries, preserves imported audio bytes, and only
rewrites an existing project through an explicit save or migration operation.
The manifest remains inspectable with standard ZIP tools while the custom
extension makes project files recognizable to VibeSound.

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
  something VibeSound redistributes.

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
uv run pytest
uv run ruff check .
uv run python -m vibesound --help
uv run vibesound version
```

The implementation is intentionally incremental. Each phase in the
[implementation plan](docs/IMPLEMENTATION_PLAN.md) has a small component
boundary, tests, and an exit criterion before the next layer is added. See the
[deployment guide](docs/DEPLOYMENT.md) for how those builds become installable
command-line releases.
