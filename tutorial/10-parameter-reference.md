# Level 10 — complete parameter reference

This page is the lookup companion to the command-by-command projects. All
paths passed to a song are relative to the folder containing `main.py`.

## Create a folder

```text
uv run prism create my-song --name "My Song" --tempo 120
```

Prism creates `projects/my-song-DATE-TIME/` and prints its exact run command.
The timestamp keeps repeated creations separate. `--name` defaults to a title
made from the folder name. `--tempo` defaults to `120` and accepts `20` through
`300` BPM. Add `--tutorial`, with or without a folder name, to create the
tutorial starting point.

## `Project(...)`

```python
song = Project(
    "Song Name",
    prism_version="0.2.0.dev0",
    tempo=120,
    sample_rate=44100,
    beats_per_bar=4,
    beat_unit=4,
    master_gain_db=-3,
    normalize=True,
)
```

| Parameter | Default | Accepted values |
| --- | --- | --- |
| `name` | required | Non-empty, at most 120 characters |
| `prism_version` | required | Keep the literal version created by Prism |
| `tempo` | `120` | 20–300 BPM |
| `sample_rate` | `44100` | 8000–192000 Hz |
| `beats_per_bar` | `4` | 1–32 |
| `beat_unit` | `4` | 1, 2, 4, 8, or 16 |
| `master_gain_db` | `-3` | -60 through +12 dB |
| `normalize` | `True` | If needed, lower the final peak to -1 dBFS |

## `track(...)`

```python
part = song.track("Readable Name", gain_db=0, pan=0, muted=False)
```

Track names are unique and at most 120 characters. Gain accepts -60 through
+12 dB. Pan runs from `-1.0` (left) through `0.0` (center) to `1.0` (right).
A muted track remains in the configuration and MIDI file structure but emits
no arranged notes or audio. Each track receives exactly one part.

## `sample(...)`

```python
part.sample("sounds/kick.wav", "x--- x---", bars=1, gain_db=0)
```

This triggers a complete source file on each hit. `x` or `*` means hit; `-` or
`.` means rest. Spaces, commas, and `|` can group the notation. Patterns contain
1–512 steps and need at least one hit. `bars` accepts 1–256 and clip gain accepts
-60 through +12 dB.

## `audio(...)`

```python
part.audio("sounds/loop.wav", bars=2, loop=True, gain_db=0)
```

This uses the complete source as one part. `loop=True` repeats or trims it to
the part length. `loop=False` plays once and pads with silence. The finished
part can repeat to fill a longer section. `bars` accepts 1–256.

Samples and audio parts accept mono or stereo formats supported by libsndfile,
including WAV and AIFF. Prism resamples to the project's sample rate. Source
paths must be relative, cannot contain `..`, and must stay inside the project.

## `drum(...)`

```python
part.drum("snare", "---- x---", bars=1, gain_db=-3, seed=0)
```

Presets are `kick`, `snare`, and `hihat`. Pattern notation matches `sample`.
The deterministic `seed` accepts 0–4294967295. A built-in drum part accepts
1–256 bars but may not exceed 120 seconds at the project's tempo and meter.

## `midi(...)`

```python
part.midi(
    "C4 Eb4 G4 C4+Eb4+G4 | - Bb3 G3 -",
    instrument="lead",
    bars=2,
    velocity=100,
    waveform="square",
    attack_ms=8,
    decay_ms=90,
    sustain=0.62,
    release_ms=140,
    cutoff_hz=3600,
    gate=0.82,
    gain_db=-6,
)
```

| Parameter | Default | Accepted values |
| --- | --- | --- |
| `notes` | required | 1–512 equal steps; `-` is rest, `+` makes a chord |
| `instrument` | `lead` | `bass`, `lead`, or `pad` |
| `bars` | `1` | 1–256 and at most 120 seconds |
| `velocity` | `100` | 1–127 |
| `waveform` | instrument preset | `sine`, `triangle`, `saw`, or `square` |
| `attack_ms` | instrument preset | 0–5000 ms |
| `decay_ms` | instrument preset | 0–5000 ms |
| `sustain` | instrument preset | 0.0–1.0 |
| `release_ms` | instrument preset | 0–5000 ms |
| `cutoff_hz` | instrument preset | 20–20000 Hz |
| `gate` | `0.8` | 0.05–1.0 of each step |
| `gain_db` | `-6` | -60 through +12 dB |

Notes use scientific pitch notation from `C-1` through `G9`, including sharps
and flats such as `F#3` and `Bb2`.

## `instrument(...)`

`midi(...)` creates a matching stock instrument automatically. Use the
separate form when you want the signal flow to be especially visible or need a
plugin object for automation:

```python
part = song.track("Lead").midi("C4 E4 G4 -", bars=2, velocity=100)
synth = part.instrument(
    "lead",
    name="Stock Lead",
    waveform="saw",
    attack_ms=8,
    decay_ms=90,
    sustain=0.62,
    release_ms=140,
    cutoff_hz=3600,
    gain_db=-6,
)
```

The presets and parameter ranges match `midi(...)`. MIDI owns the notes,
`bars`, `velocity`, and `gate`; the instrument owns waveform, envelope, cutoff,
and instrument gain. `instrument()` follows `midi()` on the same track.

## `effect(...)`

```python
drive = part.effect("distortion", name="Drive", drive_db=12, mix=0.5)
echo = part.effect(
    "delay", name="Echo", time_beats=0.5, feedback=0.25, mix=0.2
)
part.effect("filter", name="Final Tone", cutoff_hz=1200, mix=1)
```

Effects process the instrument output in the order they are added. Calling
`effect()` several times builds a top-to-bottom chain.

| Stock effect | Parameters and defaults | Accepted values |
| --- | --- | --- |
| `gain` | `gain_db=0` | -60 through +12 dB |
| `filter` | `cutoff_hz=1200`, `mix=1` | 20–20000 Hz; mix 0–1 |
| `distortion` | `drive_db=12`, `mix=0.5` | drive 0–36 dB; mix 0–1 |
| `delay` | `time_beats=0.5`, `feedback=0.25`, `mix=0.2` | time 0.03125–4 beats; feedback 0–0.95; mix 0–1 |

The returned `Plugin` object identifies the exact effect and can be saved in a
readable variable for automation.

## `automation(...)`

```python
song.automation(
    "Echo Build",
    target=echo,
    parameter="mix",
    points=[(0, 0.0), (4, 0.2), (8, 0.7)],
    curve="linear",
)
```

Each point is `(bar, value)`, measured from the beginning of the complete song.
Bars are zero or greater, strictly increasing, and cannot finish beyond the
arrangement. `linear` moves smoothly between values; `hold` keeps the previous
value until the next point. One plugin parameter can have one automation lane.

Every stock-effect setting is automatable. Stock instruments expose
`gain_db`; melodic instruments also expose `cutoff_hz`. The target must be a
plugin object belonging to the same project.

## `section(...)`

```python
song.section("Intro", bars=2, tracks=[pad, "Lead"])
song.section("Full Song", bars=8)
```

Sections are appended in playback order. Names are unique and at most 120
characters; bars accepts 1–256. A `tracks=` list accepts track objects or exact
track names. Omitting it plays every track. Each track's part loops as needed
to fill the section.

## Validate, inspect, export, and render

```python
summary = song.validate()
configuration = song.configuration()
midi = song.export_midi("renders/song.mid")
render = song.render("renders/song.wav")
```

- `validate()` checks the complete song and returns name, track count, section
  count, bar count, and duration.
- `configuration()` returns a resolved dictionary containing the complete song
  description, instruments, ordered effects, and automation lanes.
- `export_midi()` returns `path`, music-track count, ticks per beat, and SHA-256.
  It exports built-in drums and MIDI tracks, not guessed notes from audio.
- `render()` returns `path`, sample rate, channels, frames, duration, SHA-256,
  and peak dBFS.

WAV outputs must end in `.wav`; MIDI outputs must end in `.mid`. Outputs must
stay inside the project and cannot replace `main.py` or a source sample. Writes
are atomic. Rendering writes a stereo PCM-16 WAV.

## Errors are authoring feedback

Prism raises `ProjectError` for invalid song descriptions and `RenderError` for
audio decoding, synthesis, or output failures. Do not bypass them: fix the
named track, section, path, note, range, or source file and run `main.py` again.
