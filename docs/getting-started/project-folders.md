# The project folder is the project

Prism keeps inputs, instructions, and outputs together:

```text
my-song-20260828-143500/
├── main.py          editable source of truth
├── vst.json         optional VST3 aliases, paths, and checksums
├── plugin-states/   optional saved VST3 states
├── sounds/          your WAV and AIFF source files
└── renders/         generated WAV and MIDI files
```

Relative paths in `main.py` are resolved from that file's project folder even
when the command is run from the repository root. For example:

```python
song.track("Kick").sample("kick.wav", "x--- x--- x--- x---")
song.render("renders/song.wav")
```

Prism searches `sounds/` and its subfolders when a unique filename is used.
Run `uv run prism samples "projects/your-project-folder"` from the repository
root to list project audio and identify duplicate names. Files outside
`sounds/` become searchable after registering their folder in `main.py`.

Prism rejects absolute sample, state, preset, and output paths that escape the
project. Copying the folder therefore copies its script, sounds, and saved
plugin states. External VST3 binaries remain installed software; `vst.json`
records their platform paths and checksums.

The visible `prism_version="..."` setting records which Prism version created
the project. Keep it in `main.py` so an old song remains understandable later.

The repository ignores `projects/` and generated `renders/`. Your private
projects and large audio outputs will not accidentally become part of Prism's
source history.
