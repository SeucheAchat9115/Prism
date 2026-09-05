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

## `song.samples`

Every project searches `sounds/` and its subfolders for unique short
filenames. Additional folders must exist inside the project:

```python
song.samples.add_folder("recordings")
print(song.samples.folders)
print(song.samples.files())
print(song.samples.find("vocal.wav"))
```

- `folders` is the ordered tuple of registered relative folders.
- `add_folder()` registers another folder and returns the same library.
- `files()` returns every supported project-relative audio path in registered
  folders.
- `find()` returns the single matching path, suggests a close filename, or
  reports every duplicate. An explicit path bypasses short-name lookup.

From the repository root,
`uv run prism samples "projects/your-project-folder"` lists project audio
without executing `main.py`. WAV, AIFF, FLAC, and OGG extensions are listed;
generated files below `renders/` are ignored.

## `sample(...)`

```python
part.sample(
    "kick.wav", "x--- x---", bars=1, gain_db=0,
    start_seconds=0, end_seconds=None, fade_in_ms=0, fade_out_ms=0,
    reverse=False, playback_rate=1, transpose_semitones=0, stretch_bars=None,
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
    "loop.wav", bars=2, loop=True, gain_db=0,
    start_seconds=0, end_seconds=None, fade_in_ms=0, fade_out_ms=0,
    reverse=False, playback_rate=1, transpose_semitones=0, stretch_bars=None,
    section=None, start_bar=0, repeat=True,
)
```

This uses the complete source as one part. `loop=True` repeats or trims it to
the part length. `loop=False` plays once and pads with silence. The finished
part can repeat to fill a longer section. `bars` accepts 1–256.

Both methods prepare the source before placing it. `start_seconds` and
`end_seconds` select a region (the end is exclusive); omit the end to use the
rest of the file. `fade_in_ms` and `fade_out_ms` smooth the prepared source.
`reverse=True` reverses it. `playback_rate` accepts 0.25–4.0, and
`transpose_semitones` accepts integer values from -24 to +24. Transposition is
sampler-style: it changes pitch and speed together. `stretch_bars`, when set,
resizes the edited source to that many project bars before looping or padding.
It accepts 0.25–256 bars.

Samples and audio parts accept mono or stereo formats supported by libsndfile,
including WAV, AIFF, FLAC, and OGG. Prism resamples to the project's sample
rate. Source paths must be relative, cannot contain `..`, and must stay inside
the project.
The resolved configuration includes `sample_folders` and complete relative
paths, so short-name convenience does not reduce reproducibility.

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
from prism import Uniwave

part.midi(
    "C4 Eb4 G4 C4+Eb4+G4 | - Bb3 G3 -",
    instrument=Uniwave.lead(),
    bars=2,
    velocity=100,
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
| `instrument` | `Uniwave()` | A `Uniwave` sound; `Uniwave.bass()`, `.lead()`, and `.pad()` are ready-made starting points |
| `bars` | `1` | 1–256 and at most 120 seconds |
| `velocity` | `100` | 1–127 |
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

## `SynthWave(...)` and `Uniwave(...)`

Uniwave is Prism's native polyphonic synthesizer. Give a MIDI clip a ready-made
sound with `Uniwave.bass()`, `Uniwave.lead()`, or `Uniwave.pad()`, or combine one
to four independently configured waves:

```python
from prism import SynthWave, Uniwave

sound = Uniwave(
    waves=(
        SynthWave("saw", level=0.7, detune_cents=-7),
        SynthWave("saw", level=0.7, detune_cents=7, phase=0.25),
        SynthWave("square", level=0.2, octave=1),
    ),
    attack_ms=8,
    decay_ms=140,
    sustain=0.65,
    release_ms=180,
    cutoff_hz=5000,
    resonance=0.15,
    drive=0.05,
    vibrato_rate_hz=5,
    vibrato_depth_cents=8,
    noise_level=0.02,
    noise_seed=0,
)
```

| `SynthWave` parameter | Default | Accepted values |
| --- | --- | --- |
| `waveform` | `"saw"` | `"sine"`, `"triangle"`, `"saw"`, or `"square"` |
| `level` | `1.0` | 0–1 |
| `octave` | `0` | Integer from -3 through +3 |
| `semitones` | `0` | Integer from -12 through +12 |
| `detune_cents` | `0` | -100 through +100 cents |
| `phase` | `0` | 0–1 of one wave cycle |

| `Uniwave` parameter | Default | Accepted values |
| --- | --- | --- |
| `waves` | One saw wave | Tuple containing 1–4 `SynthWave` objects |
| `attack_ms` | `8` | 0–5000 ms |
| `decay_ms` | `140` | 0–5000 ms |
| `sustain` | `0.65` | 0–1 |
| `release_ms` | `180` | 0–5000 ms |
| `cutoff_hz` | `5000` | 20–20000 Hz |
| `resonance` | `0.15` | 0–0.95 |
| `drive` | `0.05` | 0–1 |
| `vibrato_rate_hz` | `5` | 0.1–20 Hz |
| `vibrato_depth_cents` | `0` | 0–100 cents |
| `noise_level` | `0` | 0–1 |
| `noise_seed` | `0` | 0–4294967295 |

Each MIDI note creates its own voice, so chords are polyphonic. Pitch bend and
modulation from `midi(...)` affect every active voice; modulation adds up to 50
cents of vibrato depth. Noise is local and seeded, so rerenders remain exact.

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
from prism import Uniwave

part = song.track("Lead").midi("C4 E4 G4 -", bars=2, velocity=100)
synth = part.instrument(
    Uniwave.lead(),
    name="Uniwave Lead",
    gain_db=-6,
)
```

The sound and parameter ranges match `midi(...)`. MIDI owns the notes, `bars`,
`velocity`, and `gate`; the Uniwave object owns its waves, envelope, tone, and
movement. `instrument()` follows `midi()` on the same track.

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

Every stock-effect setting is automatable. Uniwave exposes its global numeric
sound controls plus `wave_N_level` and `wave_N_detune_cents` for each wave in
the sound. The target must be a plugin object belonging to the same project.

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
render = song.render(
    "renders/song.wav",
    bit_depth=24,
    channels="stereo",
    sample_rate=48_000,
    tail_seconds=3,
)
stems = song.render_stems(
    "renders/stems",
    bit_depth=32,
    channels="stereo",
    sample_rate=48_000,
    tail_seconds=3,
)
```

- `validate()` checks the complete song and returns name, track count, section
  count, bar count, and duration.
- `configuration()` returns a resolved dictionary containing the complete song
  description, clips, instruments, track routing, sends, bus and master effect
  chains, and automation lanes.
- `export_midi()` returns `path`, music-track count, ticks per beat, and SHA-256.
  It exports built-in drums and MIDI tracks, not guessed notes from audio.
- `render()` returns `path`, sample rate, channels, frames, duration, SHA-256,
  peak dBFS, bit depth, and requested tail seconds.
- `render_stems()` returns one aligned WAV per track and bus plus the final
  master. Its result contains `directory`, audio format and duration fields,
  `generation`, ordered `tracks` and `buses`, `master`, and a convenient
  `files` collection. `directory` points to the completed versioned generation
  inside the requested output container.
  Each `StemFile` contains `name`, `kind`, `path`, SHA-256, and peak dBFS.

Both rendering methods accept the same keyword options:

| Option | Default | Accepted values |
| --- | --- | --- |
| `bit_depth` | `16` | `16` PCM, `24` PCM, or `32` floating point |
| `channels` | `"stereo"` | `"mono"` or `"stereo"` |
| `sample_rate` | Project rate | 8000–192000 Hz, or omit it |
| `tail_seconds` | `0` | 0–60 seconds |

WAV outputs must end in `.wav`; MIDI outputs must end in `.mid`. Outputs must
stay inside the project and cannot replace `main.py` or a source sample. A
single-file WAV uses atomic replacement. Stem WAVs are staged as a generation
and the ownership record is published afterward; the complete set is not
claimed to be one multi-file atomic transaction. `render_stems()` accepts a
relative folder instead of a filename.
Rendering defaults to stereo PCM-16 WAV files; the quality options above can
change that delivery format. See [Level 17](17-render-stems.md) for the exact
signal included in each stem.
See [Level 18](18-export-quality-and-tails.md) for choosing delivery settings
and preserving instrument and effect tails.

## Errors are authoring feedback

Prism raises `ProjectError` for invalid song descriptions and `RenderError` for
audio decoding, synthesis, or output failures. Do not bypass them: fix the
named track, section, path, note, range, or source file and run `main.py` again.
