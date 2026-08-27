# Level 5 — shape instruments and mix deliberately

Goal: use the sound-design and mixer controls without making the project file
hard to scan.

## Keep responsibilities visible

- `Project(...)` owns tempo, sample rate, meter, and master level.
- `track(...)` owns channel gain, pan, and mute.
- `midi(...)`, `drum(...)`, `sample(...)`, or `audio(...)` owns the musical
  part and its clip-level gain.
- `section(...)` owns the linear arrangement.

## Write the complete `main.py`

```python
from prism import Project, Uniwave


song = Project(
    "Shaped Synth Study",
    prism_version="0.2.0.dev0",
    tempo=96,
    master_gain_db=-4,
    normalize=True,
)

kick = song.track("Kick", gain_db=-2).drum(
    "kick",
    "x--- x--- x-x- x---",
)

bass = song.track("Bass", gain_db=-5, pan=-0.15).midi(
    "C2 - C2 - | Eb2 - G1 Bb1",
    instrument=Uniwave.bass(),
    bars=2,
    gate=0.72,
    velocity=108,
)

pad = song.track("Pad", gain_db=-12, pan=-0.35).midi(
    "C3+Eb3+G3 - | Ab2+C3+Eb3 -",
    instrument=Uniwave.pad(),
    bars=2,
    gate=0.95,
    velocity=76,
)

lead = song.track("Lead", gain_db=-10, pan=0.35).midi(
    "G4 Bb4 C5 - | G4 F4 Eb4 -",
    instrument=Uniwave.lead(),
    bars=2,
    gate=0.68,
    velocity=92,
)

song.section("Build", bars=2, tracks=[pad])
song.section("Low End", bars=2, tracks=[kick, bass, pad])
song.section("Full", bars=4)

summary = song.validate()
print(summary)
print(song.export_midi("renders/song.mid"))
result = song.render("renders/song.wav")
print(result)
print("Peak dBFS:", result.peak_dbfs)
```

## Render and compare changes

Run the command Prism printed for your timestamped tutorial project.

Open `renders/song.wav` inside the project folder.

Try one control at a time:

1. Change `Uniwave.lead()` to `Uniwave.pad()` and hear the slower envelope.
2. Change `Uniwave.bass()` to `Uniwave()` and hear the brighter default sound.
3. Move Pad pan from `-0.35` to `0.35`.
4. Set `muted=True` in `song.track("Lead", ...)`.

Rerender after each change. Small, named parameters make experiments obvious
in version control and easy to undo.

Checkpoint: you can separate composition, synthesis, channel mixing, and master
output decisions while keeping the complete song readable.
