# Prism tutorial: one song, one Python file

This is the only Prism learning path. Each level contains a complete `main.py`
that you can copy, run, change, rerun, and listen to. It starts with one sound
and ends with a structured mini-song that is comfortable for both a music
producer and a coding agent to edit.

Run the setup once from the Prism repository root:

```powershell
uv sync --locked --extra dev
uv run prism create tutorial-song --name "Tutorial Song" --tempo 120
```

Use any text editor to save the level's Python block as
`tutorial-song\main.py`. Run and listen with:

```powershell
uv run python .\tutorial-song\main.py
Start-Process .\tutorial-song\renders\song.wav
```

## Learning path

| Level | Tutorial | What you build |
| --- | --- | --- |
| 0 | [Create a project](00-create-a-project.md) | A runnable, unpacked project folder |
| 1 | [First render](01-first-render.md) | One built-in drum track and a WAV |
| 2 | [Use your own samples](02-use-your-own-samples.md) | A project-local kick sample pattern |
| 3 | [Write MIDI](03-write-midi.md) | Bass, chords, lead, WAV, and `.mid` |
| 4 | [Build a mini-song](04-build-a-mini-song.md) | Six tracks and four arranged sections |
| 5 | [Shape and mix](05-shape-and-mix.md) | Synth controls, gain, pan, and variation |
| 6 | [Work with an agent](06-work-with-an-agent.md) | A safe, readable agent-assisted workflow |
| 7 | [Audio loops and one-shots](07-audio-loops-and-one-shots.md) | Complete-file playback with and without looping |
| 8 | [Inspect and reproduce](08-inspect-and-reproduce.md) | Configuration, result metadata, hashes, and rerenders |
| 9 | [Complete reference project](09-complete-reference-project.md) | Every Prism authoring feature in one song |
| 10 | [Parameter reference](10-parameter-reference.md) | Every public method, option, range, and result field |

Levels are independent: every page shows the whole `main.py`, not only a diff.
You can replace the file at each level or put each level in a separate folder.

## The project folder is the project

`Project(__file__, ...)` makes the directory containing `main.py` the root.
Prism accepts only relative sample and output paths beneath that directory.
That means copying the folder also copies every input needed for rendering.

The producer authors:

```text
tutorial-song/
├── main.py
└── sounds/
    └── your samples.wav
```

Prism generates:

```text
tutorial-song/
├── renders/
│   ├── song.wav
│   └── song.mid
└── .prism/
    └── project.json
```

The generated manifest is useful for checking exactly which script and sample
bytes produced a render. `main.py` remains the editable source of truth.

## Complete functionality map

| Prism feature | Tutorial |
| --- | --- |
| Folder scaffolding and overwrite safety | Level 0 |
| Project name, tempo, sample rate, time signature, master gain, normalization | Levels 5 and 9 |
| Built-in kick, snare, and hi-hat | Levels 1, 4, and 9 |
| Triggered project-local samples | Levels 2 and 9 |
| Full audio loops and one-shots | Levels 7 and 9 |
| Bass, lead, pad, rests, accidentals, and chords | Levels 3 and 9 |
| Waveform, ADSR, cutoff, gate, velocity, and clip gain | Levels 5 and 9 |
| Track gain, pan, and mute | Levels 5 and 9 |
| Explicit and all-track sections | Levels 4 and 9 |
| Validation and resolved configuration | Level 8 |
| Standard MIDI export | Levels 3, 8, and 9 |
| WAV render results and deterministic manifest hashes | Levels 8 and 9 |
| Safe relative paths and agent-assisted editing | Levels 6 and 9 |
| Exact defaults, ranges, and return values | Level 10 |
