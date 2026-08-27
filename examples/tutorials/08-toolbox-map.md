# Level 8 — toolbox map and troubleshooting

Use this page after the guided song to choose the right Prism surface and to
diagnose common problems without editing project internals.

## Load and inspect an existing project

In Terminal A:

```powershell
uv run prism serve path\to\song.prism-work --open
```

In Terminal B:

```powershell
uv run prism server status path\to\song.prism-work --json
uv run prism project show path\to\song.prism-work --json
uv run prism project state path\to\song.prism-work --json
uv run prism project validate path\to\song.prism-work --json
uv run prism entity list path\to\song.prism-work track --json
uv run prism entity list path\to\song.prism-work scene --json
uv run prism entity list path\to\song.prism-work clip --json
uv run prism entity list path\to\song.prism-work asset --json
```

For a portable archive with no running service:

```powershell
uv run prism project show path\to\song.prism --portable --json
uv run prism project validate path\to\song.prism --portable --json
```

## Choose the control surface

| Task | Preferred surface |
| --- | --- |
| One finite, auditable action | `uv run prism ... --json` |
| A multi-step Python controller or agent | `prism.api.PrismClient` + typed models |
| Human clip launching and mixing | Packaged browser at the service root |
| Non-Python integration | `/api/v1` after capabilities and schema discovery |
| Repository implementation or tests | Source modules plus the repository agent guide |

## CLI family map

```powershell
uv run prism --help
uv run prism project --help
uv run prism synth --help
uv run prism transaction --help
uv run prism entity --help
uv run prism session --help
uv run prism transport --help
uv run prism audio --help
uv run prism render --help
uv run prism job --help
uv run prism events --help
uv run prism plugin --help
```

## If live playback is silent

1. Confirm that transport is playing and clips are active:

   ```powershell
   uv run prism project state prism-tutorial.prism-work --json
   ```

2. Check available stereo outputs:

   ```powershell
   uv run prism audio devices prism-tutorial.prism-work --json
   ```

3. Preview and restart an exact device:

   ```powershell
   uv run prism audio restart prism-tutorial.prism-work --device 3 --dry-run --json
   uv run prism audio restart prism-tutorial.prism-work --device 3 --json
   ```

4. Check track mute, solo, gain, and the selected scene in the browser.
5. Render a WAV. A successful non-silent render isolates the problem to live
   device setup rather than project authoring.

A missing device is a supported device-free state, not project corruption.

## If a command reports project mismatch

The service at the selected URL owns a different project. Do not bypass the
check. Stop that foreground process or use another loopback port:

```powershell
uv run prism serve another.prism-work --port 8766
uv run prism server status another.prism-work --url http://127.0.0.1:8766 --json
```

Set `PRISM_URL` when many commands use the same alternate port:

```powershell
$env:PRISM_URL = "http://127.0.0.1:8766"
```

## If a transaction fails

- `stale_revision`: re-read state, rebuild the desired operation, and preview.
- `cascade_required`: inspect `cascade_impact`; add `cascade:true` only when the
  dependent deletion is intended.
- `runtime_reset_required`: review the preview and opt in explicitly only when
  resetting live runtime is acceptable.
- `idempotency_conflict`: the key was reused for different intent; do not hide
  it by blind retries.

```powershell
uv run prism transaction preview prism-tutorial.prism-work operations.json --json
uv run prism project validate prism-tutorial.prism-work --json
```

## If a VST3 effect is unavailable

```powershell
uv run prism plugin list --json
uv run prism plugin compatibility prism-tutorial.prism-work --json
uv run prism plugin worker-status prism-tutorial.prism-work --json
```

`untrusted`, `changed`, and `missing` are intentional safety states. Never trust
a binary automatically. VST3 failures do not affect the built-in native synth.

## Automated companions

| Script | What it verifies |
| --- | --- |
| `01_project_archive.py` | Portable persistence and validation |
| `02_make_beat.py` | Generated multi-track beat |
| `03_session_performance.py` | Quantized launching and events |
| `04_render_song.py` | Arrangement and deterministic rerender |
| `05_cli_agent_workflow.py` | Complete CLI lifecycle |
| `06_transaction_safety.py` | Preview, validation, and stale revisions |
| `07_api_client.py` | HTTP and WebSocket protocol |
| `08_backend_comparison.py` | Fake versus offline backends |
| `09_audio_device_diagnostics.py` | Opt-in PortAudio diagnostics |
| `10_agent_producer_workflow.py` | Agent edit/render/reopen workflow |
| `11_browser_session.py` | Opt-in browser session |
| `12_reproducible_poc.py` | Exact installed-package acceptance |
| `13_vst3_effect.py` | Opt-in isolated VST3 effect workflow |
| `14_native_synth_song.py` | Native drums, instruments, scenes, and mini-song render |

Run the complete device-free native synth example:

```powershell
uv run python examples/14_native_synth_song.py
```

Its JSON output reports the project, track/scene list, render path, peak, hash,
and layered validation result.
