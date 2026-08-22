# Manual examples

The examples are the runnable guide to the feature set that exists today. Run
them from the repository root after installing the development environment:

```powershell
uv sync --extra dev
```

Each artifact-producing example creates a unique run directory under
`examples/output/` by default. That directory is ignored by Git. Use
`--output-dir PATH` to choose another base directory.

| Example | Demonstrates | Hardware required |
| --- | --- | --- |
| `project_archive.py` | Create, populate, reload, and validate a `.vibesound` ZIP project | No |
| `cli_workflow.py` | The current project, validation, migration, and asset-import CLI commands | No |
| `session_engine.py` | Quantized clip launch, deterministic rendering, events, and stop scheduling | No |
| `offline_render.py` | Archive-backed float32 WAV rendering through `OfflineRenderBackend` | No |
| `fake_backend.py` | The audio backend lifecycle and controls without opening a device | No |
| `portaudio_playback.py` | Real-time playback through a stereo PortAudio output | Yes |

Run the device-free examples with:

```powershell
uv run python examples/project_archive.py
uv run python examples/cli_workflow.py
uv run python examples/session_engine.py
uv run python examples/offline_render.py
uv run python examples/fake_backend.py
```

To try real-time playback on Windows, first inspect the available devices and
then optionally select an exact index or name:

```powershell
uv run python examples/portaudio_playback.py
uv run python examples/portaudio_playback.py --device 3 --seconds 5
```

The PortAudio example is intentionally opt-in and is not part of the ordinary
test suite. It uses generated audio and the current default configuration of
512-frame blocks and four queued blocks.

## Keeping examples current

Examples cover the implemented surface only. There are deliberately no API,
browser, or VST examples until those phases are implemented. When a phase adds
or changes a public feature:

1. Update the affected example or add a small new one.
2. Update this index and its command/output prerequisites.
3. Keep hardware- or plugin-dependent examples opt-in and clearly marked.
4. Update `tests/test_examples.py` for every device-free example.

The implementation plan records this as a gate for each future phase.
