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
no arranged notes or audio. A track can hold several clips of the same kind so
they share one instrument, effect chain, gain, and pan.

## `sample(...)`

```python
part.sample(
    "sounds/kick.wav", "x--- x---", bars=1, gain_db=0,
    section=None, start_bar=0, repeat=True,
)
```

This triggers a complete source file on each hit. `x` or `*` means hit; `-` or
`.` means rest. Spaces, commas, and `|` can group the notation. Patterns contain
1–512 steps and need at least one hit. `bars` accepts 1–256 and clip gain accepts
-60 through +12 dB.

## `audio(...)`

```python
part.audio(
    "sounds/loop.wav", bars=2, loop=True, gain_db=0,
    section=None, start_bar=0, repeat=True,
)
```

This uses the complete source as one part. `loop=True` repeats or trims it to
the part length. `loop=False` plays once and pads with silence. The finished
part can repeat to fill a longer section. `bars` accepts 1–256.

Samples and audio parts accept mono or stereo formats supported by libsndfile,
including WAV and AIFF. Prism resamples to the project's sample rate. Source
paths must be relative, cannot contain `..`, and must stay inside the project.

## `drum(...)`

```python
part.drum(
    "snare", "---- x---", bars=1, gain_db=-3, seed=0,
    section=None, start_bar=0, repeat=True,
)
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
    section=None,
    start_bar=0,
    repeat=True,
)
```

| Parameter | Default | Accepted values |
| --- | --- | --- |
| `notes` | required | Compact equal-step notation or a non-empty list of `Note` objects |
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
| `section` | `None` | A section name, or `None` for the default clip |
| `start_bar` | `0` | Zero or greater; relative to the section start |
| `repeat` | `True` | Repeat to the section end, or play once |
| `pitch_bend` | `()` | Increasing `(beat, semitones)` points; values -2 through +2 |
| `modulation` | `()` | Increasing `(beat, amount)` points; amounts 0–1 |
| `swing` | `0.5` | 0.5 straight through 0.75 strongly swung |
| `humanize_timing_ms` | `0` | 0–50 ms of seeded timing variation |
| `humanize_velocity` | `0` | 0–30 velocity steps of seeded variation |
| `humanize_seed` | `0` | 0–4294967295 |

Notes use scientific pitch notation from `C-1` through `G9`, including sharps
and flats such as `F#3` and `Bb2`.

For individual positions, lengths, and velocities, import `Note` and pass a
list instead of compact notation:

```python
from prism import Note

lead.midi(
    [
        Note("C4", start=0, duration=0.75, velocity=92),
        Note("E4", start=1.25, duration=0.5, velocity=108),
        Note("G4", start=2, duration=1.5, velocity=120),
    ],
    bars=1,
    pitch_bend=[(0, 0), (1, 2), (2, 0)],
    modulation=[(0, 0), (2, 1), (4, 0)],
    swing=0.62,
    humanize_timing_ms=6,
    humanize_velocity=4,
    humanize_seed=42,
)
```

`start`, `duration`, and controller positions are measured in beats from the
clip start. Notes must start and finish inside the clip. Pitch bend and
modulation move linearly between their points in the WAV and are written as
standard pitch-wheel and modulation-wheel messages in the MIDI file.

Swing delays notes placed exactly on offbeat eighth notes. Humanization adds a
bounded timing and velocity variation. Its seed makes the resolved performance
identical on every render; `configuration()` shows those resolved note values.

The compact string form still uses the clip-wide `velocity` and `gate` values.
Explicit `Note` objects use their own velocities and durations instead.

## Clip placement and section variations

The `sample(...)`, `audio(...)`, `drum(...)`, and `midi(...)` methods can be
called several times on one track. Every call adds another clip.

```python
kick = song.track("Kick").drum("kick", "x---")
kick.drum("kick", "x-x-", section="Chorus")
kick.drum("kick", "xxxx", section="Chorus", start_bar=3, repeat=False)
```

The first clip is the default for every active section. Because the track has
clips specifically for `Chorus`, those clips replace its default during that
section. Several clips for the same section are mixed together. `start_bar`
can be fractional, and must fall before the end of its named section.

Clips on one track must use the same content type and instrument. MIDI clips
also share the same synth settings; call `instrument(...)` once after adding
them when you want to change the sound of every MIDI clip together.

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
| `chorus` | `rate_hz=0.8`, `depth_ms=6`, `mix=0.3` | rate 0.05–10 Hz; depth 0–20 ms; mix 0–1 |
| `reverb` | `room_size=0.55`, `damping=0.35`, `width=0.8`, `mix=0.25` | room 0–1; damping 0–0.95; width and mix 0–1 |
| `compressor` | `threshold_db=-18`, `ratio=4`, `attack_ms=10`, `release_ms=100`, `makeup_db=0`, `mix=1` | threshold -60–0 dB; ratio 1–20; attack 0.1–200 ms; release 5–2000 ms; makeup 0–24 dB; mix 0–1 |
| `tremolo` | `rate_hz=5`, `depth=0.6`, `stereo_phase_deg=0`, `mix=1` | rate 0.05–20 Hz; depth and mix 0–1; stereo phase 0–180° |

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

## `bus(...)`

```python
drums = song.bus(
    "Drum Bus", tracks=[kick, snare, hat], gain_db=-1, pan=0, muted=False
)
drums.effect("compressor", threshold_db=-18, ratio=3, makeup_db=2)
```

A bus groups several tracks behind one gain, pan, mute control, and ordered
effect chain. Grouped tracks stop routing directly to the master. A track can
belong to only one group bus. Add more tracks later with `drums.add(clap)`.

Bus names are unique. Gain accepts -60 through +12 dB and pan accepts -1
through +1. Bus effects use the same presets, parameters, ordering, and
automation behavior as track effects.

## `send(...)`

```python
room = song.bus("Room Return", gain_db=-7)
room.effect("reverb", room_size=0.6, damping=0.4, width=1, mix=1)
snare.send(room, gain_db=-10)
lead.send(room, gain_db=-14)
```

A send adds a post-fader copy of the track to a bus while leaving its main
route intact. Send gain defaults to -12 dB and accepts -60 through +12 dB.
Each track can send to a bus once. A track cannot send to its own group bus.
Use `mix=1` on a return effect when you want a fully wet parallel effect.

## `master_effect(...)`

```python
master = song.master_effect(
    "compressor", name="Master Control", threshold_db=-8, ratio=2
)
```

Master effects run in the order they are added, after direct tracks and buses
have been combined and before `master_gain_db` and normalization. The returned
plugin can be used as an automation target like a track or bus effect.

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
  description, clips, instruments, track routing, sends, bus and master effect
  chains, and automation lanes.
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
