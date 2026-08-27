# Prism

Prism lets you make a song in one readable Python file. Your samples stay next
to that file, and running it creates a WAV you can listen to and a MIDI file you
can open in music software. A Prism project is an ordinary folder that you can
copy, back up, or share.

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
from prism import Project

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
    instrument="bass",
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
)
```

Keeping every sound inside the song folder makes the project portable. Prism
rejects absolute paths and paths that leave the project folder.

## The musical building blocks

- `drum(...)` creates a built-in `kick`, `snare`, or `hihat`.
- `sample(...)` triggers your sound with a rhythm such as `x--- x---`.
- `audio(...)` plays a complete loop or one-shot.
- `midi(...)` writes notes and renders a built-in `bass`, `lead`, or `pad`.
- `section(...)` puts parts into the song in playback order.
- `validate()` checks the project and explains authoring mistakes.
- `export_midi()` writes a standard MIDI file.
- `render()` writes a stereo WAV.

In rhythm patterns, `x` is a hit and `-` is a rest. In MIDI parts, `-` is a
rest and `C3+Eb3+G3` is a chord.

## Continue with the tutorial

Create a timestamped tutorial workspace directly from the CLI:

```text
uv run prism create --tutorial
```

Then open the [step-by-step tutorial](tutorial/README.md). It covers samples,
audio loops, MIDI, arrangement, synthesis, mixing, reproducible renders, and
every available setting using the folder and run command Prism printed.

## Checks for Prism contributors

Most music producers can ignore this section.

```text
uv sync --locked --extra dev
uv run pytest --cov --cov-report=term-missing
uv run mypy src/prism
uv run ruff check .
uv build --no-sources
```
