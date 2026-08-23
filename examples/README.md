# Manual examples

The examples are the runnable guide to the VibeSound features that exist today.
They use a generated, deterministic five-track beat where possible, so users
can explore project creation, session control, rendering, the CLI, the API, and
agent workflows without supplying their own audio files.

Run them from the repository root after installing the development environment:

```powershell
uv sync --extra dev
```

For the Phase 5.5 installed-package acceptance flow, create the synthetic demo
and start its loopback service with `vibesound demo demo.vibesound-work`. Add
`--no-serve` when only generating and reopening the fixture in automation.

Artifact-producing examples create a unique run directory under
`examples/output/` by default. That directory is ignored by Git. Use
`--output-dir PATH` to choose another base directory.

## Numbered examples

| # | Example | Demonstrates | Hardware |
| --- | --- | --- | --- |
| 01 | [`01_project_archive.py`](01_project_archive.py) | Create, populate, reload, and validate a `.vibesound` ZIP project | No |
| 02 | [`02_make_beat.py`](02_make_beat.py) | Generate drums, bass, pad, tracks, scenes, mixer settings, and a rendered beat preview | No |
| 03 | [`03_session_performance.py`](03_session_performance.py) | Quantized scene launching, looping, scene switching, events, and stop scheduling | No |
| 04 | [`04_render_song.py`](04_render_song.py) | Render an eight-bar arrangement and verify byte-identical rerendering | No |
| 05 | [`05_cli_agent_workflow.py`](05_cli_agent_workflow.py) | Use the current `version`, `doctor`, project, validation, migration, and asset-import CLI commands | No |
| 06 | [`06_transaction_safety.py`](06_transaction_safety.py) | Preview and commit agent transactions, validate values, and reject stale revisions | No |
| 07 | [`07_api_client.py`](07_api_client.py) | Use HTTP and WebSocket API routes for state, transport, clip controls, transactions, events, and rendering | No |
| 08 | [`08_backend_comparison.py`](08_backend_comparison.py) | Compare deterministic fake playback with the offline render backend | No |
| 09 | [`09_audio_device_diagnostics.py`](09_audio_device_diagnostics.py) | Inspect stereo PortAudio devices and optionally play a generated clip | Opt-in |
| 10 | [`10_agent_producer_workflow.py`](10_agent_producer_workflow.py) | Simulate an agent inspecting, editing, rendering, hashing, and reopening a song | No |

## Run the device-free examples

```powershell
uv run python examples/01_project_archive.py
uv run python examples/02_make_beat.py
uv run python examples/03_session_performance.py
uv run python examples/04_render_song.py
uv run python examples/05_cli_agent_workflow.py
uv run python examples/06_transaction_safety.py
uv run python examples/07_api_client.py
uv run python examples/08_backend_comparison.py
uv run python examples/10_agent_producer_workflow.py
```

The generated project and WAV files are printed as JSON. The most approachable
starting point is [02 — make a beat](02_make_beat.py); open its generated WAV
and inspect its `.vibesound` archive with standard ZIP tools. The best example
for a coding agent is [10 — agent producer workflow](10_agent_producer_workflow.py).

## Run the hardware example

First list stereo-capable devices without starting playback:

```powershell
uv run python examples/09_audio_device_diagnostics.py
```

Then optionally select an exact device index or name and play the generated
signal:

```powershell
uv run python examples/09_audio_device_diagnostics.py --device 3 --play-seconds 5
uv run python examples/09_audio_device_diagnostics.py --device "Speakers" --play-seconds 5
```

This example is intentionally excluded from the normal test suite. A missing
audio device is an environment condition, not a code failure; playback errors
are reported with the backend snapshot.

## What is not included yet

There are no browser, VST3, MIDI, arrangement-editing, automation, routing, or
recording examples yet because those product phases are not implemented. Each
future phase must add the smallest numbered example for its new public surface,
document its prerequisites here, and keep external-device or plugin examples
opt-in.

## Keeping examples current

For every public feature change:

1. Update the affected numbered example or add the next available number.
2. Update this index, the command, prerequisites, and expected artifact.
3. Keep deterministic examples in the ordinary smoke-test suite.
4. Keep browser, hardware, and plugin examples explicitly opt-in.
5. Update [`tests/test_examples.py`](../tests/test_examples.py).

The phase-by-phase maintenance gate is tracked in the
[`implementation plan`](../docs/IMPLEMENTATION_PLAN.md).
