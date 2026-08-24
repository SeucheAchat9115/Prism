# Manual examples

The examples are the runnable guide to the Prism features that exist today.
They use a generated, deterministic five-track beat where possible, so users
can explore project creation, session control, rendering, the CLI, the API, and
agent workflows without supplying their own audio files.

Run them from the repository root after installing the development environment:

```powershell
uv sync --extra dev
```

For the installed-package acceptance flow, create the synthetic demo and start
its loopback service with `prism demo demo.prism-work`. Add `--open` for
the Phase 7 browser session or `--no-serve` when automation only needs the
fixture. Example 12 drives the complete Phase 8 workflow against a selected
Prism installation.

Artifact-producing examples create a unique run directory under
`examples/output/` by default. That directory is ignored by Git. Use
`--output-dir PATH` to choose another base directory.

## Numbered examples

| # | Example | Demonstrates | Hardware |
| --- | --- | --- | --- |
| 01 | [`01_project_archive.py`](01_project_archive.py) | Create, populate, reload, and validate a `.prism` ZIP project | No |
| 02 | [`02_make_beat.py`](02_make_beat.py) | Generate drums, bass, pad, tracks, scenes, mixer settings, and a rendered beat preview | No |
| 03 | [`03_session_performance.py`](03_session_performance.py) | Quantized scene launching, looping, scene switching, events, and stop scheduling | No |
| 04 | [`04_render_song.py`](04_render_song.py) | Render an eight-bar arrangement and verify byte-identical rerendering | No |
| 05 | [`05_cli_agent_workflow.py`](05_cli_agent_workflow.py) | Run the Phase 6 foreground service and exercise discovery, import, transactions, entities, session, transport, jobs, render, export, and portable inspection through the CLI | No |
| 06 | [`06_transaction_safety.py`](06_transaction_safety.py) | Preview and commit agent transactions, validate values, and reject stale revisions | No |
| 07 | [`07_api_client.py`](07_api_client.py) | Use HTTP and WebSocket API routes for state, transport, clip controls, transactions, events, and rendering | No |
| 08 | [`08_backend_comparison.py`](08_backend_comparison.py) | Compare deterministic fake playback with the offline render backend | No |
| 09 | [`09_audio_device_diagnostics.py`](09_audio_device_diagnostics.py) | Inspect stereo PortAudio devices and optionally play a generated clip | Opt-in |
| 10 | [`10_agent_producer_workflow.py`](10_agent_producer_workflow.py) | Simulate an agent inspecting, editing, rendering, hashing, and reopening a song | No |
| 11 | [`11_browser_session.py`](11_browser_session.py) | Create the synthetic demo, start its foreground loopback service, and open the Phase 7 studio UI | Browser, opt-in |
| 12 | [`12_reproducible_poc.py`](12_reproducible_poc.py) | Drive the canonical fixture through browser launches, CLI control, safe transactions, rendering, shutdown, and reopen | Chromium, opt-in |
| 13 | [`13_vst3_effect.py`](13_vst3_effect.py) | Trust, discover, attach, control, state-round-trip, restart, and offline-render one user-installed VST3 effect | VST3 + `plugins` extra, opt-in |

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

The generated project and WAV files are printed as JSON. Example 05 takes about
one to two minutes because it launches each installed command in a fresh process
and shuts its foreground service down cleanly. The most approachable
starting point is [02 — make a beat](02_make_beat.py); open its generated WAV
and inspect its `.prism` archive with standard ZIP tools. The best example
for a coding agent is [10 — agent producer workflow](10_agent_producer_workflow.py).

## Run the browser examples

The Phase 7 browser example blocks while its local service is running and is
therefore excluded from the normal example suite. It uses the system browser
and needs no Node installation:

```powershell
uv run python examples/11_browser_session.py
```

Press Ctrl+C in that terminal to stop the service. Use `--no-open` to print and
serve the URL without launching a browser, or pass `--port` to select another
local port.

The Phase 8 example uses Playwright to run the complete acceptance flow
headlessly and leaves a JSON report, service logs, browser trace, working
project, and rendered WAV in a unique output directory:

```powershell
uv run python -m playwright install chromium
uv run python examples/12_reproducible_poc.py
```

Add `--headed` to watch Chromium. Use `--app-python PATH` to drive a clean wheel
installed in a different Python environment.

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

## Run the VST3 example

Install the optional worker host and provide a licensed effect already present
on your machine:

```powershell
uv sync --extra dev --extra plugins
uv run python examples/13_vst3_effect.py --plugin "C:\Path\Example.vst3"
```

The example redirects machine policy into its unique output directory, trusts
the exact supplied bytes, scans in isolation, attaches one effect to the demo,
round-trips parameters and opaque state, restarts/reloads the worker, and writes
an offline WAV. Use `--registry-id` when one VST3 container exposes multiple
effects. It is excluded from device-free smoke tests because Prism does not ship
a third-party VST3 fixture.

## What is not included yet

There are no live VST3, plugin-instrument, MIDI, arrangement-editing,
automation, routing, or recording examples yet because those product phases are
not implemented. Each future phase must add the smallest numbered example for
its new public surface, document its prerequisites here, and keep external-
device, browser, or plugin examples opt-in.

## Keeping examples current

For every public feature change:

1. Update the affected numbered example or add the next available number.
2. Update this index, the command, prerequisites, and expected artifact.
3. Keep deterministic examples in the ordinary smoke-test suite.
4. Keep browser, hardware, and plugin examples explicitly opt-in.
5. Update [`tests/test_examples.py`](../tests/test_examples.py).

The phase-by-phase maintenance gate is tracked in the
[`implementation plan`](../docs/IMPLEMENTATION_PLAN.md).
