# Phase 9 isolated VST3 worker

Phase 9 adds opt-in VST3 audio effects to Prism's offline render path while
preserving the Phase 8 device-free baseline. Third-party code is never imported
or executed in the application process. One subprocess owns plugin discovery,
instances, parameters, opaque state, and audio processing; the main process
owns trust, project revisions, storage, jobs, and events.

Live transport remains dry. Phase 9 supports effects, not plugin instruments,
MIDI, automation, plugin editors, multi-effect chains, or real-time hosting.

## Install the optional host

The normal development and wheel installations do not require Pedalboard:

```powershell
uv sync --locked --extra dev
```

Install the explicit optional extra to probe or process a real VST3:

```powershell
uv sync --locked --extra dev --extra plugins
```

Prism does not install, copy, or redistribute third-party plugins. Supply a
VST3 already installed under its own license.

## Trust and registry model

Machine-local configuration defaults to:

```text
%APPDATA%\Prism\plugins.json
%APPDATA%\Prism\plugin-registry.json
```

Set `PRISM_PLUGIN_CONFIG` to redirect the policy file; the registry remains
adjacent to it. This is useful for testing or isolated agent runs. Neither file
is embedded in `.prism` projects.

Search paths and trust are intentionally separate:

1. A search path makes `.vst3` files/bundles discoverable.
2. Prism hashes each candidate deterministically.
3. A user explicitly allowlists one resolved path and exact SHA-256.
4. A scan probes only candidates whose current bytes match that record.
5. Changed bytes become untrusted until explicitly approved again.

The local registry records a stable UUID, resolved load path, shell/plugin
identifier, binary hash, display metadata, availability, trust, and any probe
error. It is an atomic cache and can be rebuilt by scanning.

## CLI workflow

Configure and inspect machine state without opening a project:

```powershell
uv run prism plugin path-add "C:\Program Files\Common Files\VST3"
uv run prism plugin trust "C:\Program Files\Common Files\VST3\Example.vst3" --json
uv run prism plugin scan --json
uv run prism plugin list --json
```

Start the normal foreground project service, then use project commands from a
second terminal:

```powershell
uv run prism serve song.prism-work

uv run prism plugin compatibility song.prism-work --json
uv run prism plugin attach song.prism-work --track Drums --registry-id REGISTRY_UUID --dry-run --json
uv run prism plugin attach song.prism-work --track Drums --registry-id REGISTRY_UUID --idempotency-key drums-fx-v1 --json
uv run prism plugin parameters song.prism-work INSTANCE_UUID --json
uv run prism plugin set song.prism-work INSTANCE_UUID gain 0.65 --dry-run --json
uv run prism plugin set song.prism-work INSTANCE_UUID gain 0.65 --idempotency-key drums-gain-v1 --json
uv run prism plugin bypass song.prism-work INSTANCE_UUID --bypassed --json
uv run prism plugin bypass song.prism-work INSTANCE_UUID --active --json
uv run prism plugin state-save song.prism-work INSTANCE_UUID --json
uv run prism plugin worker-status song.prism-work --json
uv run prism plugin worker-restart song.prism-work --json
uv run prism render song.prism-work --bars 8 --output effected.wav --json
uv run prism plugin remove song.prism-work INSTANCE_UUID --dry-run --json
```

`--dry-run` uses server-backed transaction preview. Mutations use the same
revision and idempotency rules as every other Prism authoring operation.

## Project schema 2

Each `Track` contains `effects`, currently bounded to zero or one
`PluginInstance`. An instance persists:

- instance and registry UUIDs;
- the worker load identifier;
- exact plugin binary SHA-256;
- name, manufacturer, version, and category;
- explicit bypass state;
- normalized raw parameter values in `[0.0, 1.0]`;
- an optional opaque state reference.

Opaque state uses this portable layout:

```text
song.prism
├── project.json
└── assets/
    ├── audio/
    │   └── <asset-id>.wav
    └── plugin-state/
        └── <instance-id>.bin
```

The reference includes member path, size, and SHA-256. Repository import,
validation, snapshots, deterministic export, and direct archive validation all
verify the bytes. State is bounded to 16 MiB by default. Plugin binaries and
machine paths never enter the portable archive. Schema 1 projects migrate in
memory to schema 2 with empty effect lists.

## Typed operations

The transaction discriminator accepts:

- `plugin.attach`
- `plugin.remove`
- `plugin.parameter.update`
- `plugin.bypass.update`
- `plugin.state.update` (used internally after state bytes are installed)

Attachment metadata must match the current trusted registry entry at service
preflight. Track deletion reports owned plugin instances in cascade impact and
requires `cascade=true`. Effect edits are offline-only project changes and do
not rebuild the live audio graph.

## API and typed client

Discovery and machine policy:

```text
GET    /api/v1/plugins/config
POST   /api/v1/plugins/search-paths
DELETE /api/v1/plugins/search-paths
POST   /api/v1/plugins/trust
DELETE /api/v1/plugins/trust
POST   /api/v1/plugins/scan
GET    /api/v1/plugins
GET    /api/v1/plugins/worker
POST   /api/v1/plugins/worker/restart
```

Project control:

```text
GET  /api/v1/projects/{project_id}/plugins/compatibility
POST /api/v1/projects/{project_id}/tracks/{track_id}/plugins/{registry_id}
GET  /api/v1/projects/{project_id}/plugins/{instance_id}/parameters
POST /api/v1/projects/{project_id}/plugins/{instance_id}/parameters/{parameter_id}
POST /api/v1/projects/{project_id}/plugins/{instance_id}/bypass
POST /api/v1/projects/{project_id}/plugins/{instance_id}/state
```

Attachment, parameter, and bypass routes accept `?preview=true`. The typed
`PrismClient` mirrors every route with `PluginAttachRequest`,
`PluginParameterRequest`, `PluginBypassRequest`, and
`PluginStateCaptureRequest` contracts.

The capabilities document reports `vst3`, `isolated_worker`, `offline_render`,
`realtime: false`, and `max_effects_per_track: 1`.

## Worker protocol and audio path

`PluginWorkerClient` starts `python -m prism.plugins.worker` without a console
window on Windows. Requests and responses are strict protocol-version-1 JSON
objects with correlated request IDs. The controller serializes requests, owns
timeouts, rejects malformed/mismatched responses, retains bounded stderr
diagnostics, and terminates a worker that violates the boundary.

Audio blocks use named shared memory rather than JSON/base64. The host sees
contiguous float32 frames in mono or stereo and must return the same shape.
Opaque state uses base64 inside the bounded control protocol.

Offline signal order is:

```text
clip source → clip gain → VST3 effect → track gain/pan/mute/solo → stereo mix
```

Effect tracks continue receiving silent blocks after clips stop so effect tails
can advance. Projects without effects take the original Phase 8 render branch.

## Failure recovery and events

The render processor validates registry identity, current trust, and all three
binary hashes (trust, registry, project) before loading. A processing failure:

1. emits `plugin.worker.failed`;
2. terminates/restarts the worker;
3. reloads healthy instances and retries the block once;
4. on repeated failure, emits `plugin.instance.bypassed` and passes dry input
   for that instance for the rest of the render.

The automatic safety bypass does not mutate the project's explicit `bypassed`
field. Consumers that require a fully effected artifact must observe plugin and
job events rather than treating a completed dry-fallback render as equivalent.

Additional events include:

- `plugin.search_paths.changed`
- `plugin.trust.changed`
- `plugin.registry.changed`
- `plugin.instance.loaded`
- `plugin.state.captured`
- `plugin.worker.restarted`

## Browser session

The Track effects panel lists compatibility per instance, scans the local
registry, attaches ready effects to empty tracks, exposes normalized parameter
sliders, toggles persisted bypass, captures state, and removes instances. The
panel labels the offline-only boundary directly. Browser actions call the same
v1 API and revisioned transaction service as the CLI and typed client.

## Verification

The ordinary device-free suite uses fake plugin metadata/workers and never
requires a third-party binary:

```powershell
uv run ruff check .
uv run mypy src/prism
uv run pytest tests/plugins tests/project/test_plugins_phase9.py tests/api/test_phase9_plugins.py
uv run pytest -m "not audio_device and not browser" --cov --cov-report=term-missing
```

Validate the real optional import/worker boundary separately:

```powershell
uv sync --locked --extra dev --extra plugins
uv run python -c "from prism.plugins import PluginWorkerClient; c=PluginWorkerClient(); c.start(); print(c.status()); c.close()"
uv run python examples/13_vst3_effect.py --plugin "C:\Path\Example.vst3"
```

The example changes only a redirected policy file inside its output directory
and remains outside the normal smoke suite because its behavior depends on a
user-installed plugin.
