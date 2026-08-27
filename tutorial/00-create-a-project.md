# Level 0 — create the tutorial project

Goal: create the folder used throughout the tutorial and render its starter song.

Open a terminal in the Prism repository root and run:

```text
uv sync --locked
uv run prism create --tutorial
```

Prism creates a timestamped folder inside `projects/`. Its name looks like:

```text
projects/tutorial-20260827-143500/
├── main.py
├── sounds/
└── renders/
```

Your timestamp will reflect the moment you ran the command. Prism prints the
exact command for your folder, for example:

```text
uv run "projects/tutorial-20260827-143500/main.py"
```

Copy and run the command Prism printed. Then open `renders/song.wav` inside the
new folder in your music player.

Keep this project folder for the remaining levels. Each page gives you a
complete replacement for its `main.py`; the run command stays the same.

Checkpoint: the timestamped folder contains an editable `main.py`, a `sounds/`
folder, and rendered WAV and MIDI files.
