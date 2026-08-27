# Level 8 — inspect and reproduce a render

Goal: inspect the resolved project configuration and the MIDI/WAV result
objects, then confirm that an unchanged song renders identically.

Replace the project’s `main.py` with:

```python
from pprint import pprint

from prism import Project, Uniwave


song = Project(
    "Reproducible Loop",
    prism_version="0.2.0.dev0",
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
    instrument=Uniwave.lead(),
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
```

Run the command Prism printed for your timestamped tutorial project.

The output includes a long SHA-256 value for the WAV. Run the same command a
second time. The WAV SHA-256 is identical when nothing changed. The printed
configuration shows the resolved tracks, parts, sections, tempo, meter, and
Prism version.
The MIDI and WAV result lines show their paths and hashes; the WAV line also
shows its format, duration, and peak level.

Checkpoint: you can explain which file is authored (`main.py`), which files are
inputs (`sounds/`), and which files are reproducibly generated (`renders/`).
