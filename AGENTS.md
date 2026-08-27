# Prism repository agent guide

These instructions apply to the entire repository. Prism is a Python 3.12,
Python-first digital audio workstation whose browser UI, CLI, and typed client
all call one loopback application service. The current product boundary is the
completed Phase 9 offline VST3 worker plus Phase 10.1 native synthesized audio
assets and progressive tutorials.

## Skill routing

Repository-scoped skills live in `.agents/skills/` and are discovered
automatically. Load the smallest set that covers the request:

- `$prism-repository-development`: implement, debug, review, test, or document
  repository changes.
- `$prism-project-authoring`: create, inspect, validate, migrate, or safely edit
  projects, native synth assets, tracks, scenes, clips, slots, transport
  settings, and mixer values.
- `$prism-session-control`: run and control a live service, transport, session
  grid, mixer, audio backend, event stream, or browser session.
- `$prism-render-export`: import audio, preview or run render/export jobs, wait
  for results, and verify artifacts.
- `$prism-api-integration`: build an agent or other client against the typed
  Python client, HTTP API, or WebSocket event stream.
- `$prism-plugin-control`: discover and explicitly trust user-installed VST3
  effects, manage project instances, parameters, bypass/state, compatibility,
  offline rendering, and isolated-worker recovery.

For a repository implementation that changes a public workflow, use
`$prism-repository-development` plus the affected domain skill. For operating
an existing project without changing Prism source, use only the domain skill.

## Choose the right tool surface

- Use `uv run prism ... --json` for finite, auditable shell operations. Prefer
  `--dry-run` or a preview command before mutations.
- Use `prism.api.PrismClient` for multi-step Python agent workflows. Construct
  request objects from `prism.application`; do not hand-roll JSON in Python.
- Use raw `/api/v1` HTTP or WebSocket calls only for non-Python integrations or
  when explicitly testing the protocol. Discover readiness, capabilities, and
  schemas first.
- Use browser automation only to validate visible UI behavior. The browser is a
  client, not the source of truth for project state.
- Use repository file tools for source changes. Do not edit a user's
  `project.json`, `.prism-work/.prism/`, or `.prism` archive directly; mutate
  projects through the service transaction and job contracts.

## Architecture map

- `src/prism/project/`: models, validation, archives, migrations, working
  repository, locks, history, staging, and cache.
- `src/prism/engine/`: deterministic transport, scheduling, sources, and sinks.
- `src/prism/rendering/`: deterministic offline render contracts and mixing.
- `src/prism/audio/`: fake, offline, and PortAudio backend boundary.
- `src/prism/plugins/`: machine-local trust/registry, versioned worker
  protocol, subprocess control, and fail-safe offline effect processing.
- `src/prism/synthesis/`: deterministic native drum/melodic specifications,
  note parsing, preset discovery, DSP, and WAV encoding.
- `src/prism/application/`: the state owner, typed operations, runtime, events,
  and background jobs.
- `src/prism/api/`: FastAPI routes, loopback server, and typed synchronous
  `PrismClient`.
- `src/prism/command_line/`: Typer CLI as a client of the service.
- `src/prism/web/`: packaged HTML, CSS, and JavaScript session client.

Preserve this dependency direction. The CLI and browser must not become state
owners or bypass `ApplicationService`. Put shared public request/response models
in `src/prism/application/types.py` and keep unknown fields rejected.

## Product invariants

- One explicit foreground service owns one project and binds only to loopback.
- `.prism-work` is editable working storage; `.prism` is a deterministic,
  immutable portable archive until an explicit migration or export.
- Compare the service project ID from readiness with the intended local project
  before sending project-scoped commands.
- Preview transactions before commit. Respect `base_revision`, cascade impact,
  runtime reset requirements, and idempotency keys.
- Render and export outputs stay inside the working project's `exports/` tree.
- Device-free fallback is valid behavior. Real-device tests remain opt-in.
- VST3 support is opt-in, effect-only, one instance per track, and offline
  render-only. Exact binary trust is machine-local; opaque state is portable.
  Never claim that live transport is plugin-processed.
- Native synthesis is built in and generates ordinary immutable WAV assets.
  It is not a VST instrument or MIDI clip. Generate and preview the asset
  through the service contract, then create clips and slots explicitly.
- Do not claim support for external plugin instruments, MIDI, recording,
  arrangement editing, automation, advanced routing, collaboration, or remote access;
  those phases are not implemented.

## Repository workflow

1. Inspect `git status` and preserve unrelated user changes.
2. Locate the owning layer before editing; use `rg` and existing tests/examples
   rather than guessing at contracts.
3. Update every affected public surface together: models/service, API, CLI or
   UI, tests, examples, and phase documentation.
4. Keep generated artifacts in ignored paths such as `examples/output/`,
   `test-results-*`, or a temporary directory.
5. Verify in proportion to the change.

Baseline setup and checks:

```powershell
uv sync --locked --extra dev
uv run ruff check .
uv run mypy src/prism
uv run pytest -m "not audio_device and not browser" --cov --cov-report=term-missing
```

Additional gates:

- API/CLI changes: run `tests/api`, `tests/project/test_cli*.py`, and the
  relevant example, especially `examples/05_cli_agent_workflow.py`.
- Browser changes: install Chromium once, then run
  `uv run pytest -m browser --browser chromium --tracing=retain-on-failure`.
- Persistence/render/audio changes: run their focused test directories and the
  affected numbered examples.
- Plugin changes: run `tests/plugins`, `tests/project/test_plugins_phase9.py`,
  and `tests/api/test_phase9_plugins.py`; keep real third-party VST3 examples
  opt-in and never add plugin binaries to fixtures.
- Release-facing changes: run `uv build --no-sources`, test the exact wheel in
  a clean environment, and run `examples/12_reproducible_poc.py` against it.

Coverage must remain at least 85% for the configured device-free package. Real
audio hardware is never a prerequisite for the ordinary gate.
