# Plugin trust, project, API, and recovery contracts

## Installation and machine state

The optional host is installed with:

```powershell
uv sync --extra plugins
```

Machine-local policy defaults to `%APPDATA%\Prism\plugins.json` on Windows and
can be redirected with `PRISM_PLUGIN_CONFIG`. The adjacent
`plugin-registry.json` is a disposable cache. Neither file belongs in a
portable project.

Trust records contain the resolved path and exact SHA-256. Search paths only
make candidates discoverable; they do not confer trust. A scan hashes all
candidates, probes matching trusted bytes in the worker, and records untrusted,
changed, unavailable, or ready entries without loading anything in the main
process.

## CLI sequence

```powershell
uv run prism plugin path-add "C:\VST3"
uv run prism plugin trust "C:\VST3\Example.vst3" --json
uv run prism plugin scan --json
uv run prism plugin list --json

uv run prism plugin compatibility song.prism-work --json
uv run prism plugin attach song.prism-work --track Drums --registry-id REGISTRY_UUID --dry-run --json
uv run prism plugin attach song.prism-work --track Drums --registry-id REGISTRY_UUID --idempotency-key attach-drums-v1 --json
uv run prism plugin parameters song.prism-work INSTANCE_UUID --json
uv run prism plugin set song.prism-work INSTANCE_UUID gain 0.65 --dry-run --json
uv run prism plugin set song.prism-work INSTANCE_UUID gain 0.65 --idempotency-key gain-v1 --json
uv run prism plugin bypass song.prism-work INSTANCE_UUID --bypassed --json
uv run prism plugin state-save song.prism-work INSTANCE_UUID --json
uv run prism plugin worker-status song.prism-work --json
uv run prism plugin worker-restart song.prism-work --json
uv run prism plugin remove song.prism-work INSTANCE_UUID --dry-run --json
```

`path-add`, `path-remove`, `trust`, `revoke`, `scan`, and `list` operate on
machine-local policy and do not require a project. Project commands verify the
local project identity through the foreground service like other Prism CLI
workflows.

## Typed Python client

```python
from prism.api import PrismClient
from prism.application import PluginAttachRequest, PluginParameterRequest

with PrismClient() as client:
    ready = client.readiness()
    registry = client.list_plugins()
    record = next(item for item in registry.plugins if item.available)
    project = client.get_project(ready.project_id)
    track = next(item for item in project.tracks if not item.effects)

    preview = client.attach_plugin(
        ready.project_id,
        track.id,
        record.registry_id,
        PluginAttachRequest(base_revision=project.revision.number),
        preview=True,
    )
```

Re-read the project after every successful commit. Use the returned revision,
not a locally incremented guess, when building the next request.

## HTTP routes

Machine-local registry and worker:

- `GET /api/v1/plugins/config`
- `POST|DELETE /api/v1/plugins/search-paths`
- `POST|DELETE /api/v1/plugins/trust`
- `POST /api/v1/plugins/scan`
- `GET /api/v1/plugins`
- `GET /api/v1/plugins/worker`
- `POST /api/v1/plugins/worker/restart`

Project-scoped control:

- `GET /api/v1/projects/{project_id}/plugins/compatibility`
- `POST /api/v1/projects/{project_id}/tracks/{track_id}/plugins/{registry_id}`
- `GET /api/v1/projects/{project_id}/plugins/{instance_id}/parameters`
- `POST /api/v1/projects/{project_id}/plugins/{instance_id}/parameters/{parameter_id}`
- `POST /api/v1/projects/{project_id}/plugins/{instance_id}/bypass`
- `POST /api/v1/projects/{project_id}/plugins/{instance_id}/state`

The attach, parameter, and bypass routes accept `?preview=true`. Removal uses a
normal `plugin.remove` transaction so cascade and revision behavior stay
visible.

## Typed operations

- `plugin.attach`: one effect on an empty track effect slot, using metadata
  copied from the current trusted registry entry.
- `plugin.parameter.update`: normalized `raw_value` in `[0, 1]`.
- `plugin.bypass.update`: persisted bypass intent.
- `plugin.state.update`: internal state-reference commit after bounded state
  bytes have been installed atomically.
- `plugin.remove`: removes the instance; its opaque state is deleted after the
  project commit succeeds.

Track deletion reports plugin instances in cascade impact and requires
`cascade=true` when a track owns an effect.

## Portable schema and render order

Schema 2 adds `Track.effects` with a maximum of one `PluginInstance`. Each
instance stores registry identity, plugin load identifier, binary hash,
display metadata, bypass, normalized parameters, and an optional hashed opaque
state reference. Schema 1 projects migrate to empty effect lists.

Offline signal order is clip gain → plugin → track gain/pan/mute/solo → mix.
Effects receive silent blocks after a clip stops so time-based tails can
continue. Projects without effects use the original dry engine path.

## Events and recovery

Observe the normal `project.changed` and job events plus:

- `plugin.registry.changed`
- `plugin.trust.changed`
- `plugin.search_paths.changed`
- `plugin.instance.loaded`
- `plugin.state.captured`
- `plugin.worker.failed`
- `plugin.worker.restarted`
- `plugin.instance.bypassed`

On a worker processing failure Prism terminates/restarts the worker, reloads
healthy snapshot instances, and retries the block once. A repeated failure
marks only that instance failed for the render and passes its dry input through.
The project manifest is not mutated by this automatic safety bypass.
