# Architecture and validation

Use this reference when deciding where a Prism change belongs or which checks
must pass. The root `AGENTS.md` contains the non-negotiable product invariants.

## Ownership map

| Concern | Primary source | Primary tests |
| --- | --- | --- |
| Project models and archive format | `src/prism/project/models.py`, `archive.py` | `tests/project/test_models.py`, `test_archive.py` |
| Working storage, locking, history, staging, cache | `src/prism/project/repository.py` | `tests/project/test_repository.py`, `test_scale.py` |
| Project and playback validation | `src/prism/project/validation.py` | project and application tests |
| Transport and clip scheduling | `src/prism/engine/` | `tests/engine/` |
| Offline render contracts and mixing | `src/prism/rendering/` | `tests/rendering/` |
| Native drum/melodic asset generation | `src/prism/synthesis/` | `tests/synthesis/`, synthesis API/CLI/application tests |
| Audio backend lifecycle | `src/prism/audio/` | `tests/audio/` |
| Transactions, runtime, events, jobs | `src/prism/application/` | `tests/application/` |
| HTTP/WebSocket and typed client | `src/prism/api/` | `tests/api/` |
| CLI parsing and JSON envelopes | `src/prism/command_line/` | `tests/project/test_cli*.py` |
| Browser session | `src/prism/web/` | `tests/api/test_phase7_ui.py`, `tests/browser/` |
| Package/release gate | `pyproject.toml`, `ci/`, `.github/workflows/ci.yml` | wheel smoke and Phase 8 acceptance |

The intended call path is:

```text
CLI / Browser / PrismClient
           |
        /api/v1
           |
   ApplicationService
      /     |      \
 project  engine  jobs/runtime
             \      /
          audio/rendering
```

Domain modules must not import the CLI or browser. Keep protocol translation in
the API/client layer and user-facing shell behavior in `command_line`.

## Public-contract checklist

When a change alters externally observable behavior, check each applicable
surface:

- `src/prism/application/types.py` for shared strict models.
- `src/prism/api/app.py` and `src/prism/api/client.py` for route/client parity.
- `src/prism/command_line/app.py` and `support.py` for CLI and JSON envelopes.
- `src/prism/web/` for browser behavior and conflict reconciliation.
- `README.md`, `docs/PHASE_*.md`, and `examples/README.md` for documented scope.
- A numbered example for every newly public workflow.

Do not silently change API error shapes, CLI exit meanings, archive member
layout, deterministic hashes, or event semantics. Additive v1 changes are
preferred. A breaking contract requires an explicit project decision and tests.

## Validation matrix

Run the smallest relevant set during iteration, then the combined gate for a
cross-layer change.

### Always for Python changes

```powershell
uv run ruff check .
uv run mypy src/prism
uv run pytest <focused tests>
```

### Full device-free source gate

```powershell
uv run pytest -m "not audio_device and not browser" --cov --cov-report=term-missing
```

Coverage is configured to fail below 85%. The real PortAudio callback module is
excluded from aggregate coverage but has mocked lifecycle tests.

### API and CLI

```powershell
uv run pytest tests/api tests/project/test_cli.py tests/project/test_cli_phase6.py tests/project/test_cli_phase7.py
uv run python examples/05_cli_agent_workflow.py
```

### Browser

```powershell
uv run python -m playwright install chromium
uv run pytest -m browser --browser chromium --tracing=retain-on-failure
```

Also inspect the actual page for layout or interaction changes.

### Persistence, engine, rendering, and audio

Run the corresponding test directory, then the affected examples. Useful
acceptance examples are:

- `02_make_beat.py` for project generation and rendering.
- `03_session_performance.py` for scheduling.
- `04_render_song.py` for deterministic rerendering.
- `06_transaction_safety.py` for revision and validation safety.
- `08_backend_comparison.py` for fake/offline parity.
- `10_agent_producer_workflow.py` for edit, render, hash, and reopen.

Use `09_audio_device_diagnostics.py` and `pytest -m audio_device -s` only when
real hardware behavior is in scope.

### Package or release-facing changes

```powershell
uv build --no-sources
```

Install the exact built wheel into a clean Python 3.12 environment. Verify the
`prism` entry point, packaged `/` and `/assets/`, and then run:

```powershell
uv run python examples/12_reproducible_poc.py --app-python <clean-python>
```

The acceptance report must end with `status: passed` and validate browser, CLI,
transactions, render hashes, shutdown, reopen, and layered validation.
