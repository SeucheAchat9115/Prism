# Level 8 — inspect and reproduce a render

Goal: inspect the resolved project configuration, MIDI/WAV result objects, and
the generated reproducibility manifest.

Replace `tutorial-song\main.py` with:

```python
from pprint import pprint

from prism import Project


song = Project(
    __file__,
    "Reproducible Loop",
    tempo=100,
    sample_rate=44100,
    beats_per_bar=4,
    beat_unit=4,
    master_gain_db=-3,
    normalize=True,
)

kick = song.track("Kick", gain_db=-3).drum("kick", "x--- x--- x--- x---")
lead = song.track("Lead", gain_db=-9, pan=0.2).midi(
    "C4 E4 G4 Bb4 | G4 E4 D4 -",
    instrument="lead",
)

song.section("Loop", bars=2, tracks=[kick, lead])

summary = song.validate()
pprint(song.configuration())

midi = song.export_midi("renders/song.mid")
render = song.render("renders/song.wav")

print(summary)
print("MIDI:", midi.path, midi.tracks, midi.ticks_per_beat, midi.sha256)
print(
    "WAV:",
    render.path,
    render.sample_rate,
    render.channels,
    render.frames,
    render.duration_seconds,
    render.peak_dbfs,
    render.sha256,
)
print("Manifest:", render.manifest_path)
```

Run it and inspect the generated manifest:

```powershell
uv run python .\tutorial-song\main.py
Get-Content .\tutorial-song\.prism\project.json
```

Prove that an unchanged rerender is byte-identical:

```powershell
$first = (Get-FileHash .\tutorial-song\renders\song.wav -Algorithm SHA256).Hash
uv run python .\tutorial-song\main.py
$second = (Get-FileHash .\tutorial-song\renders\song.wav -Algorithm SHA256).Hash
$first
$second
$first -eq $second
```

The last command should print `True`. The manifest records the resolved song,
script hash, source hashes, render format, duration, peak, and output hash.

Checkpoint: you can explain which file is authored (`main.py`), which files are
inputs (`sounds/`), and which files are reproducibly generated (`renders/` and
`.prism/project.json`).
