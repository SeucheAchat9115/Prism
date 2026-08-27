# Prism tutorial: one song, one Python file

This is the only Prism learning path. Each level contains a complete `main.py`
that you can copy, run, change, rerun, and listen to. It starts with one sound
and ends with a structured mini-song that is comfortable for both a music
producer and a coding agent to edit.

Run the setup once from the Prism repository root:

```powershell
uv sync --locked --extra dev
New-Item -ItemType Directory -Force .\tutorial-song\sounds | Out-Null
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
| 1 | [First render](01-first-render.md) | One built-in drum track and a WAV |
| 2 | [Use your own samples](02-use-your-own-samples.md) | A project-local kick sample pattern |
| 3 | [Write MIDI](03-write-midi.md) | Bass, chords, lead, WAV, and `.mid` |
| 4 | [Build a mini-song](04-build-a-mini-song.md) | Six tracks and four arranged sections |
| 5 | [Shape and mix](05-shape-and-mix.md) | Synth controls, gain, pan, and variation |
| 6 | [Work with an agent](06-work-with-an-agent.md) | A safe, readable agent-assisted workflow |

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
