# The project folder is the project

Prism keeps inputs, instructions, and outputs together:

```text
my-song-20260828-143500/
├── main.py          editable source of truth
├── sounds/          your WAV and AIFF source files
└── renders/         generated WAV and MIDI files
```

Relative paths in `main.py` are resolved from that file's project folder even
when the command is run from the repository root. For example:

```python
song.track("Kick").sample("sounds/kick.wav", "x--- x--- x--- x---")
song.render("renders/song.wav")
```

Prism rejects absolute paths and paths that escape the project. Copying the
folder therefore copies the script and every local sound it needs.

The visible `prism_version="..."` setting records which Prism version created
the project. Keep it in `main.py` so an old song remains understandable later.

The repository ignores `projects/` and generated `renders/`. Your private
projects and large audio outputs will not accidentally become part of Prism's
source history.
