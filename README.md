# Prism

Prism is a Python package for writing reproducible songs. A music project is a
normal folder whose `main.py` describes its tracks, samples, MIDI notes,
arrangement, mix, and render.

There is no Prism server, browser interface, hidden database, archive, or
proprietary project file. Prism's small CLI only creates a starting folder;
the editable Python script remains the interface for making and rendering music.

## The complete idea

```text
my-song/
├── main.py                 authored song and configuration
├── sounds/
│   └── kick.wav            project-local source audio
├── renders/
│   ├── my-song.wav         generated stereo mix
│   └── my-song.mid         generated MIDI arrangement
└── .prism/
    └── project.json        generated plan and source/render hashes
```

Create a normal project folder:

```powershell
uv run prism create my-first-song --tempo 120
cd .\my-first-song
uv run python .\main.py
Start-Process .\renders\song.wav
```

The command creates directories and files directly—never a ZIP file:

```text
my-first-song/
├── main.py
├── sounds/
└── renders/
```

A small `main.py` can be this direct:

```python
from prism import Project

song = Project(__file__, "My First Song", tempo=120)

kick = song.track("Kick", gain_db=-3).drum(
    "kick",
    "x--- x--- x--- x---",
)

bass = song.track("Bass", gain_db=-6).midi(
    "C2 - C2 Eb2 | G1 - Bb1 -",
    instrument="bass",
    bars=2,
)

song.section("Intro", bars=2, tracks=[bass])
song.section("Beat", bars=4, tracks=[kick, bass])

print(song.validate())
print(song.export_midi("renders/my-first-song.mid"))
print(song.render("renders/my-first-song.wav"))
```

Run it like any Python program:

```powershell
uv run python .\my-song\main.py
Start-Process .\my-song\renders\my-first-song.wav
```

## Install for development

Prism currently targets Python 3.12.

```powershell
git clone https://github.com/SeucheAchat9115/Prism.git
cd Prism
uv sync --locked --extra dev
```

Applications that consume the package need only Prism's normal dependencies:
NumPy, SoundFile, and SoXR. PortAudio, FastAPI, browser tooling, and VST hosting
are not part of the package.

## Create command

```text
prism create FOLDER [--name "Song Name"] [--tempo BPM]
```

`prism create` refuses to overwrite an existing path. It writes a complete,
runnable `main.py` plus empty `sounds/` and `renders/` folders. After creation,
all work happens in that ordinary folder with normal Python and audio files.
`python -m prism create ...` is equivalent when console scripts are unavailable.

## Public workflow

1. Construct `Project(__file__, ...)` so all relative paths use the folder that
   contains the producer's script.
2. Add named tracks with `song.track(...)`.
3. Give each track exactly one readable part:
   `drum(...)`, `sample(...)`, `audio(...)`, or `midi(...)`.
4. Append named sections in playback order with `song.section(...)`.
5. Call `validate()`, optionally `export_midi()`, then `render()`.

Important behavior:

- `drum("kick" | "snare" | "hihat", pattern)` uses deterministic built-in
  sounds.
- `sample("sounds/kick.wav", pattern)` triggers a mono or stereo project-local
  sample with an `x---` pattern.
- `audio("sounds/loop.wav")` plays or loops a complete audio file.
- `midi("C4 - E4 G4", instrument="lead")` creates real note data and renders
  it through the built-in `bass`, `lead`, or `pad` instrument.
- `+` makes a chord, `-` makes a rest, spaces and `|` can visually group a bar.
- Sections choose which tracks play and determine the final linear arrangement.
- Source and output paths must stay inside the project folder. This prevents a
  project from depending silently on a producer's machine-specific absolute
  path.

## Reproducibility

Prism's source of truth is `main.py` plus files beneath the project folder.
Rendering writes `.prism/project.json`, which records:

- the fully resolved tempo, meter, tracks, parts, mix, and sections;
- the SHA-256 of `main.py` and every external sample;
- output format, duration, frame count, peak, and SHA-256.

Given the same script, sample bytes, Prism version, and platform-compatible
audio libraries, repeated renders are byte-identical PCM-16 WAV files. Prism
writes outputs atomically, so a failed render does not replace a good file.

## Learn Prism

The [progressive tutorial](tutorial/README.md) covers project creation, every
track type, all built-in instruments, MIDI export, arrangement, mixing, synth
controls, configuration inspection, manifests, deterministic rerendering, and
safe collaboration with an agent. Every practical level contains complete
commands and a full `main.py`.

## Scope

Prism is intentionally an offline, script-first package. Its CLI only creates
project folders; it does not edit, play, or render songs. Prism does not provide
an HTTP/WebSocket API, GUI, live playback engine, session server, VST host,
recording system, ZIP project archive, or mutable project database. Python code
is the music interface and the reproducible project format.

## Development

```powershell
uv run pytest --cov --cov-report=term-missing
uv run mypy src/prism
uv run ruff check .
uv build --no-sources
```

The tests exercise only the public Python workflow and device-free offline
rendering. No audio hardware is required.
