# Prism step-by-step tutorials

This is the human learning path for Prism. Every tutorial is command by command,
uses only redistributable sounds until the optional VST3 level, and leaves a
checkpoint you can inspect or listen to.

The tutorials use PowerShell 7 on Windows and assume commands run from the
repository root. Install the exact locked development environment once:

```powershell
uv sync --locked --extra dev
uv run prism doctor --json
```

## Learning path

| Level | Tutorial | Result | Time | Requirements |
| --- | --- | --- | --- | --- |
| 0 | [Listen to the demo](00-listen-to-the-demo.md) | Hear a supplied drum and synth scene; render a WAV | 10 min | Audio device optional |
| 1 | [Make one synth sound](01-make-one-synth-sound.md) | Create, load, play, and render a native lead | 15 min | None |
| 2 | [Build a drum loop](02-build-a-drum-loop.md) | Program kick, snare, and hi-hat tracks | 20 min | Level 1 project |
| 3 | [Build a mini-song](03-build-a-mini-song.md) | Add bass, pad, lead, four scenes, an eight-bar mix, and a portable project | 35 min | Levels 1–2 project |
| 4 | [Shape, mix, and edit safely](04-shape-mix-and-edit.md) | Design a patch, swap audio, preview transactions, and test stale-edit safety | 25 min | Level 3 project |
| 5 | [Control Prism with Python](05-control-with-python.md) | Use the typed API, events, session controls, and a render job | 25 min | Level 3 project |
| 6 | [Perform in the browser](06-perform-in-the-browser.md) | Launch scenes, mix, watch events, and render from the UI | 15 min | Level 3 project + browser |
| 7 | [Add a VST3 effect](07-add-a-vst3-effect.md) | Trust and apply a user-installed effect to an offline render | 25 min | Licensed VST3 + plugins extra |
| 8 | [Toolbox map and troubleshooting](08-toolbox-map.md) | Choose the right interface and diagnose playback, service, or project issues | Reference | Varies |

Levels 1–4 deliberately build the same `prism-tutorial.prism-work` project.
Finish them in order. Level 0 uses a separate demo and can be run at any time.

## Two-terminal convention

Prism has one explicit foreground service per project. A tutorial therefore
uses:

- **Terminal A** for `prism serve`; leave it running.
- **Terminal B** for finite commands such as authoring, playback, and render.
- **Terminal C** only when watching the event stream.

Stop Terminal A with Ctrl+C before serving another project on the same port.
Prism never starts a hidden daemon.

## What “native synth” means

`prism synth generate` is a built-in deterministic instrument. It turns drum
patterns, notes, rests, and chords into a loop-aligned WAV asset and imports it
through the same revisioned transaction path as any other audio. The resulting
clip works in live playback, the browser, offline renders, and portable
projects. It needs no VST, MIDI device, plugin trust, or audio hardware.

It is intentionally not represented as a third-party plugin instance. Prism’s
VST3 host remains effect-only and offline-only; external VST3 instruments and
MIDI are later product work.

## Listening versus rendering

- Live listening requires a usable stereo output device. Prism reports a
  device-free fallback instead of failing when one is unavailable.
- Offline render always works without hardware and produces a WAV beneath the
  project’s `exports/` directory.
- `Start-Process $Render.data.output_path` opens a completed WAV in the Windows
  default audio player.

Generated tutorial projects and WAVs are local artifacts. Do not commit them.
The automated companion is
[`14_native_synth_song.py`](../14_native_synth_song.py); it builds the complete
mini-song device-free in one command for regression testing.
