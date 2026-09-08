# Agent contract

Prism exposes a read-only, provider-neutral inspection boundary for a person
and an external coding agent. It is intentionally local: it does not call an
LLM, use a network connection, open an audio device, or mutate `main.py`.
Building a project executes its reviewed Python `build() -> Project` function,
using the task-14 build boundary.

## Contract and operations

The contract name is `prism.agent`, with `schema_version=1` and
`contract_version=1`. The public Python API is:

```python
from prism import (
    agent_capabilities,
    agent_operation,
    build_agent_operation,
    inspect_agent_context,
    select_agent_entities,
)

capabilities = agent_capabilities(song)
context = inspect_agent_context(song)
selected = select_agent_entities(
    song,
    {"entity": "track", "role": "bass", "quarter_note_range": [0, 16]},
)
result = agent_operation(
    song,
    {"operation": "inspect", "revision_id": context["revision_id"]},
)
```

For a project folder, `build_agent_operation(path, request)` first executes
`build()` and then returns the same result envelope. The three operations are:

| Operation | Purpose |
| --- | --- |
| `capabilities` | Discover supported operations, entity types, limits, and execution requirements. |
| `inspect` | Return bounded arrangement, musical, routing, plugin, asset, and render context. |
| `select` | Resolve entities by stable ID, role, section, name, or quarter-note range. |

Every operation result carries `project_id`, `revision_id`, and
`selected_ranges`. Errors are structured as `error.code`, `error.message`, and
`error.details`; unsupported schema versions, stale revisions, unknown IDs,
and ambiguous names never fall back to a guess.

## Identities and migration

`identity_schema_version=1` adds stable IDs for projects, tracks, sections,
clip definitions, compiled clip instances, buses, and plugins. Names remain in
the response as display fields. Explicit IDs are available on `Project`,
`Project.track`, `Project.section`, and clip methods. Without one, Prism assigns
deterministic authoring-order IDs that do not contain display names. A repeated
placement receives a distinct clip-instance ID for each section occurrence.

Existing Python projects do not need a source rewrite. Rebuilding them assigns
the same deterministic IDs for the same authoring order, and configuration
migration fills missing identity fields in older snapshots. Declare explicit
IDs when a project must keep identity through reordering or moving files.

Duplicate display names are valid when tracks have explicit IDs (or when a
fixture explicitly opts into them with `allow_duplicate_name=True`). Selecting
a duplicate by name returns `ambiguous_name` with candidate IDs; select by ID
or by a musical role instead.

## Known intent and inference

The `musical_context.authored` object contains only values declared by the
producer: `key`, `scale`, and `chords`, each marked `source: authored`. Per-track
roles are also authored when passed to `song.track(..., role=...)`.

Register and rhythmic summaries are derived from compiled events and marked
`source: inferred` with a provenance method. Inferred harmony is a bounded
pitch-class estimate with an `uncertainty` value and provenance. It is a prompt
for human listening and editing decisions, never an authored key or a claim
about musical quality.

## CLI

The machine-readable CLI always prints JSON for these commands:

```console
prism agent capabilities
prism agent inspect path/to/song --json
prism agent select path/to/song --entity track --role bass --start-beat 0 --end-beat 16 --json
prism agent operation path/to/song '{"operation":"inspect"}' --json
```

Use `--limits '{"max_notes":128,"max_clip_instances":64}'` to make a
request smaller. Missing optional VST3 binaries or hosts appear as unavailable
plugin metadata; native offline context remains inspectable.

::: prism.agent
    options:
      members:
        - AgentLimits
        - AgentOperationRequest
        - agent_capabilities
        - agent_operation
        - build_agent_operation
        - inspect_agent_context
        - project_revision_id
        - select_agent_entities
