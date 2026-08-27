# Level 9 — complete Prism reference project

Goal: use every producer-facing authoring feature in one readable project.

Prepare three files you own or have permission to use:

```powershell
Copy-Item C:\path\to\kick.wav .\tutorial-song\sounds\kick.wav
Copy-Item C:\path\to\percussion-loop.wav .\tutorial-song\sounds\percussion-loop.wav
Copy-Item C:\path\to\vocal-shot.wav .\tutorial-song\sounds\vocal-shot.wav
```

Replace `tutorial-song\main.py` with this complete reference:

```python
from pprint import pprint

from prism import Project


song = Project(
    __file__,
    "Complete Prism Song",
    tempo=112,
    sample_rate=44100,
    beats_per_bar=4,
    beat_unit=4,
    master_gain_db=-4,
    normalize=True,
)

sample_kick = song.track("Sample Kick", gain_db=-2).sample(
    "sounds/kick.wav", "x--- x--- x--- x---", bars=1, gain_db=-1
)
built_in_kick = song.track("Built-In Kick", gain_db=-5).drum(
    "kick", "x--- x--- x-x- x---"
)
loop = song.track("Percussion Loop", gain_db=-8, pan=-0.1).audio(
    "sounds/percussion-loop.wav", bars=2, loop=True, gain_db=-2
)
vocal = song.track("Vocal One-Shot", gain_db=-7, pan=0.25).audio(
    "sounds/vocal-shot.wav", bars=2, loop=False
)
snare = song.track("Snare", gain_db=-8).drum(
    "snare", "---- x--- ---- x---", seed=11
)
hat = song.track("Hi-Hat", gain_db=-13, pan=0.3).drum(
    "hihat", "x-x- x-x- x-x- x-x-", seed=17
)
bass = song.track("Bass", gain_db=-6, pan=-0.15).midi(
    "C2 - C2 Eb2 | G1 - Bb1 -",
    instrument="bass", bars=2, velocity=105, waveform="saw",
    attack_ms=5, decay_ms=100, sustain=0.58, release_ms=110,
    cutoff_hz=900, gate=0.78, gain_db=-4,
)
pad = song.track("Pad", gain_db=-12, pan=-0.3).midi(
    "C3+Eb3+G3 - | Ab2+C3+Eb3 -",
    instrument="pad", bars=2, velocity=85, waveform="triangle",
    attack_ms=180, decay_ms=380, sustain=0.76, release_ms=420,
    cutoff_hz=2400, gate=0.92, gain_db=-6,
)
lead = song.track("Lead", gain_db=-10, pan=0.35).midi(
    "C4 D4 Eb4 G4 | Bb4 G4 Eb4 -",
    instrument="lead", bars=2, velocity=96, waveform="square",
    attack_ms=8, decay_ms=90, sustain=0.62, release_ms=140,
    cutoff_hz=3600, gate=0.82, gain_db=-6,
)
muted_idea = song.track("Muted Sine Idea", muted=True).midi(
    "C5 - G4 -", instrument="lead", waveform="sine"
)

song.section("Intro", bars=2, tracks=[built_in_kick, loop, pad])
song.section("Verse", bars=4, tracks=[sample_kick, snare, hat, loop, bass, pad])
song.section("Chorus", bars=4)
song.section("Outro", bars=2, tracks=[vocal, pad, lead, muted_idea])

print(song.validate())
pprint(song.configuration())
print(song.export_midi("renders/complete-song.mid"))
print(song.render("renders/complete-song.wav"))
```

Run, inspect, and listen:

```powershell
uv run python .\tutorial-song\main.py
Get-Content .\tutorial-song\.prism\project.json
Start-Process .\tutorial-song\renders\complete-song.wav
```

This project demonstrates triggered samples, looping audio, one-shots, all
three drums, all three melodic instruments, all four waveforms, chords, rests, every synth control,
track and clip gain, panning, muting, explicit sections, an all-track section,
validation, configuration inspection, MIDI export, WAV rendering, and the
reproducibility manifest.

All input and output paths are relative to `main.py`. Prism rejects absolute
paths, `..` traversal, missing sources, duplicate names, empty tracks, unknown
section tracks, unsafe output paths, and attempts to overwrite source files.

Checkpoint: this folder is a complete, copyable Prism project. Copy the folder,
install the same Prism version, and run `main.py`; no ZIP import step exists.
