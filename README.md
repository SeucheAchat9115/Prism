# Prism

Prism lets you make a song in one readable Python file. Your samples stay next
to that file, and running it creates a WAV you can listen to and a MIDI file you
can open in music software. A Prism project is an ordinary folder that you can
copy, back up, or share.

**[Read the complete Prism documentation](https://seucheachat9115.github.io/Prism/)**

It includes installation help, the complete step-by-step tutorial, playable
audio, musical guides, plugin development instructions, troubleshooting, and a
Python reference generated from the package.

## Quick start

Open a terminal in the Prism repository folder. Keep it there for every command;
you never need to enter the song folder.

### 1. Install uv once

If `uv --version` already works, skip this step.

Windows PowerShell:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Linux:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Close and reopen the terminal after installation if `uv` is not found.
Other installation choices are listed in the
[official uv installation guide](https://docs.astral.sh/uv/getting-started/installation/).

### 2. Prepare Prism once

```text
uv sync --locked
```

uv prepares the correct Python version and everything Prism needs.

### 3. Create and render your first song

```text
uv run prism create my-song
```

Prism adds the current date and time and prints the exact next command. It looks
like this:

```text
uv run "projects/my-song-20260827-143500/main.py"
```

Copy that printed command whenever you want to render the song. Both Windows
and Linux accept it from the repository root. To listen, open the new project
in your file manager and double-click `renders/song.wav`.

## What Prism created

```text
projects/
└── my-song-20260827-143500/
    ├── main.py                 your song
    ├── sounds/                 put your WAV or AIFF files here
    └── renders/
        ├── song.wav            finished audio
        └── song.mid            MIDI for other music software
```

The timestamp keeps each new project separate. The whole `projects/` folder is
ignored by Git. `main.py` is the file you edit, while `renders/` is recreated
when you run it.

## What `main.py` looks like

```python
from prism import Project, Uniwave

song = Project(
    "My Song",
    prism_version="0.2.0.dev0",
    tempo=120,
)

kick = song.track("Kick", gain_db=-3).drum(
    "kick",
    "x--- x--- x--- x---",
)

bass = song.track("Bass", gain_db=-6).midi(
    "C2 - C2 Eb2 | G1 - Bb1 -",
    instrument=Uniwave.bass(),
    bars=2,
)

song.section("Loop", bars=4, tracks=[kick, bass])

print(song.validate())
print(song.export_midi("renders/song.mid"))
print(song.render("renders/song.wav"))
```

Prism automatically knows that the folder containing the running `main.py` is
the project folder. This is why the printed `uv run "projects/.../main.py"`
command works while your terminal stays in the repository root.

`prism_version` is written as plain text when the project is created. Leave it
in the file: it tells you which Prism version the project started with.

## Make changes

Open the timestamped project’s `main.py` in any text editor. Change a note,
rhythm, tempo, or mix setting, save the file, and run the command Prism printed
when the folder was created:

```text
uv run "projects/my-song-20260827-143500/main.py"
```

Prism replaces the generated WAV and MIDI with the new version. If the script
and samples have not changed, the WAV is reproduced byte for byte.

## Use your own sounds

Copy sounds into the project’s `sounds/` folder, then refer to them with a short
relative path:

```python
kick = song.track("Sample Kick").sample(
    "sounds/kick.wav",
    "x--- x--- x--- x---",
)

texture = song.track("Texture").audio(
    "sounds/texture.wav",
    bars=4,
    loop=True,
    start_seconds=0.25,
    end_seconds=8.25,
    fade_in_ms=12,
    fade_out_ms=40,
    stretch_bars=4,
)
```

Keeping every sound inside the song folder makes the project portable. Prism
rejects absolute paths and paths that leave the project folder.

## The musical building blocks

- `drum(...)` creates a built-in `kick`, `snare`, or `hihat`.
- `sample(...)` triggers your sound with a rhythm such as `x--- x---`.
- `audio(...)` plays a complete loop or one-shot.
- `midi(...)` writes notes and renders Prism's built-in Uniwave synthesizer.
- `Note(...)` gives individual MIDI notes their own position, length, and velocity.
- `instrument(...)` separates a MIDI part from its stock synthesizer settings.
- `effect(...)` adds ordered stock dynamics, tone, modulation, delay, and reverb plugins.
- `automation(...)` moves a plugin setting at exact song positions in bars.
- `section(...)` puts parts into the song in playback order.
- Repeating a part method adds clips, section variations, and precisely placed fills.
- `bus(...)` groups tracks or creates a shared effect return.
- `send(...)` routes a parallel post-fader copy of a track to a bus.
- `master_effect(...)` processes the complete mix before final output.
- `validate()` checks the project and explains authoring mistakes.
- `export_midi()` writes a standard MIDI file.
- `render()` writes a stereo WAV.

In rhythm patterns, `x` is a hit and `-` is a rest. In MIDI parts, `-` is a
rest and `C3+Eb3+G3` is a chord.

## Instruments, effects, and automation

Prism follows a familiar music-production signal flow:

```text
Song → Section → Track → Instrument → Track effects → Buses → Master effects → Mix
```

MIDI notes and drum/sample trigger patterns decide what plays and when. A stock
instrument turns those events into sound. Effects process that sound from top
to bottom in the order you add them. A track can contain several effects.

```python
from prism import Uniwave

lead = song.track("Lead", gain_db=-8).midi(
    "C4 E4 G4 Bb4 | G4 E4 D4 -",
    bars=2,
    velocity=96,
    instrument=Uniwave.lead(),
)

synth = lead.instrument(
    Uniwave.lead(),
    name="Uniwave Lead",
)

echo = lead.effect(
    "delay",
    name="Echo",
    time_beats=0.5,
    feedback=0.3,
    mix=0.15,
)

lead.effect("chorus", name="Width", rate_hz=0.8, depth_ms=6, mix=0.25)
lead.effect("reverb", name="Room", room_size=0.55, damping=0.35, mix=0.2)
lead.effect("filter", name="Final Tone", cutoff_hz=4000)

song.automation(
    "Echo Build",
    target=echo,
    parameter="mix",
    points=[(0, 0.0), (4, 0.15), (8, 0.6)],
)
```

Automation positions are absolute bars from the beginning of the song. Values
move smoothly by default; use `curve="hold"` for an immediate change. Stock
instrument gain and cutoff can also be automated. Uniwave additionally exposes
its envelope, filter, drive, vibrato, noise, and per-wave controls.

Tracks can also contain several clips while sharing the same instrument and
effects. A default clip plays wherever the track is active. A clip with a
section name replaces that default in the named section:

```python
kick = song.track("Kick").drum("kick", "x---")
kick.drum("kick", "x-x-", section="Chorus")
kick.drum("kick", "xxxx", section="Chorus", start_bar=3, repeat=False)
```

Shared processing uses a group bus, while a send keeps the dry track and adds
a parallel copy to a return bus:

```python
drums = song.bus("Drum Bus", tracks=[kick, snare, hat])
drums.effect("compressor", threshold_db=-18, ratio=3)

room = song.bus("Room Return", gain_db=-7)
room.effect("reverb", room_size=0.6, mix=1)
snare.send(room, gain_db=-10)

song.master_effect("compressor", name="Master Control", threshold_db=-8, ratio=2)
```

For a performed part instead of equal steps, place individual notes in beats
and add reproducible feel and controller movement:

```python
from prism import Note

lead = song.track("Lead").midi(
    [
        Note("G4", start=0, duration=1.5, velocity=92),
        Note("C5", start=2, duration=1, velocity=118),
    ],
    pitch_bend=[(0, 0), (1, 2), (2, 0)],
    modulation=[(0, 0), (2, 1), (4, 0)],
    swing=0.62,
    humanize_timing_ms=6,
    humanize_velocity=4,
    humanize_seed=42,
    instrument=Uniwave.lead(),
)
```

## Continue with the tutorial

Create a timestamped tutorial workspace directly from the CLI:

```text
uv run prism create --tutorial
```

Then open the [step-by-step tutorial](docs/tutorial/README.md). It covers samples,
audio loops, MIDI, arrangement, synthesis, mixing, reproducible renders, and
every available setting using the folder and run command Prism printed.

## Checks for Prism contributors

Most music producers can ignore this section.

To extend Prism itself, follow
[Adding a stock plugin](docs/plugins/adding-stock-plugins.md). It covers instruments,
effects, automation, MIDI mappings, deterministic DSP, tests, and documentation.

```text
uv sync --locked --extra dev
uv run pytest --cov --cov-report=term-missing
uv run mypy src/prism
uv run ruff check .
uv build --no-sources
```
