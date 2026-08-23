# Phase 8 reproducible POC acceptance

Phase 8 closes the first VibeSound proof of concept with one repeatable workflow
that crosses the packaged browser, CLI, transaction, renderer, and working-project
boundaries. The blocking gate runs against the exact built wheel on a clean
Windows runner without an audio device or third-party plugins.

This phase proves release readiness; it does not publish `0.1.0.dev0`, create a
tag, or add a PyPI/GitHub Release workflow.

## Canonical fixture

A fresh `vibesound demo` destination is created in one atomic transaction at
revision 1. Its generated audio and UUID5-derived entity IDs are deterministic
for that project ID. Existing non-empty demo paths remain untouched.

| Element | Phase 8 value |
| --- | --- |
| Transport | 120 BPM, 4/4, bar quantization, 44.1 kHz |
| Tracks | Drums, Synth |
| Scenes | Verse, Chorus |
| Media | Two generated half-second mono WAV assets |
| Session grid | Four clips and four populated slots |
| Drums mixer | -3 dB, -0.25 pan, unmuted |
| Synth mixer | -9 dB, +0.25 pan, muted |

The original Phase 7 Drums, Synth, Verse, Chorus, Verse clip, and Verse slot
identifiers are preserved. Chorus clip and slot identifiers use the same stable
project-scoped naming scheme.

## Run the acceptance flow

Install the development environment and Chromium, then run:

```powershell
uv sync --locked --extra dev
uv run python -m playwright install chromium
uv run python examples/12_reproducible_poc.py
```

Chromium is headless by default. Add `--headed` to watch the session, use
`--output-dir PATH` to choose the artifact root, or pass `--app-python PATH` to
test a VibeSound installation in another Python environment.

The runner performs these checks through public browser and CLI contracts:

1. Create a fresh canonical demo and verify revision 1.
2. Start the loopback service and load the packaged browser session.
3. Launch the Verse clips for both tracks in Chromium.
4. Launch the Drums/Chorus clip through a separate CLI process and observe the
   browser switch without reloading.
5. Commit Drums gain and Synth mute changes together, reaching revision 2.
6. Preview an invalid 99 dB change, require a validation failure, and verify the
   project is still revision 2 with the committed mixer values.
7. Render Chorus from frame zero for one bar and verify the WAV path, job hash,
   file hash, sample rate, channel count, and 88,200-frame duration.
8. Stop the service, reopen the project in a new service process, verify revision
   2 and its exact content, and run layered validation.

Every VibeSound subprocess is launched with the interpreter selected by
`--app-python`. Playwright remains a driver dependency and is not installed into
or imported by the application under test.

## Artifacts and failure handling

Each invocation creates a unique `phase8-poc-*` directory containing:

- the working project and rendered `exports/phase8-poc.wav`;
- valid, invalid, and render command JSON files;
- `phase8-acceptance.json` with step, revision, and WAV metadata;
- CLI and service logs;
- a Playwright trace; and
- a full-page screenshot when browser interaction fails.

Foreground services are stopped in cleanup paths on both success and failure.
Logs stream directly to disk so verbose access logging cannot block the service
subprocess.

## CI gate

The ordinary Windows/Linux validation and Ubuntu Chromium jobs still exercise
the source checkout. The dependent Windows packaging job then:

1. builds the wheel and source archive;
2. installs the exact wheel into a clean Python 3.12 environment with runtime
   dependencies only;
3. runs the installed CLI and packaged-UI smoke checks; and
4. drives the complete Phase 8 acceptance example against that interpreter.

The driver environment contains Playwright, but neither the clean wheel
environment nor the fixture installs the optional `plugins` extra. Acceptance
reports, logs, traces, and screenshots are retained when the CI step fails.
