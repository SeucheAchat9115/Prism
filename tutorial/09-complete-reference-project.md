# Level 9 — complete Prism reference project

Goal: use every producer-facing authoring feature in one readable project.

Using your file manager, put three files you own into the project’s `sounds/` folder:
`kick.wav`, `percussion-loop.wav`, and `vocal-shot.wav`.

Replace the project’s `main.py` with this complete reference:

```python
from pprint import pprint

from prism import Project


song = Project(
    "Complete Prism Song",
    prism_version="0.2.0.dev0",
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
    bars=2, velocity=96, gate=0.82,
)
lead_synth = lead.instrument(
    "lead", name="Stock Lead", waveform="square",
    attack_ms=8, decay_ms=90, sustain=0.62, release_ms=140,
    cutoff_hz=3600, gain_db=-6,
)
lead.effect("distortion", name="Lead Drive", drive_db=8, mix=0.2)
lead_echo = lead.effect(
    "delay", name="Lead Echo", time_beats=0.5, feedback=0.3, mix=0.1
)
lead_tone = lead.effect("filter", name="Lead Tone", cutoff_hz=5000, mix=1)
sample_kick.effect("gain", name="Kick Trim", gain_db=-1)
muted_idea = song.track("Muted Sine Idea", muted=True).midi(
    "C5 - G4 -", instrument="lead", waveform="sine"
)

song.section("Intro", bars=2, tracks=[built_in_kick, loop, pad])
song.section("Verse", bars=4, tracks=[sample_kick, snare, hat, loop, bass, pad])
song.section("Chorus", bars=4)
song.section("Outro", bars=2, tracks=[vocal, pad, lead, muted_idea])

song.automation(
    "Lead Synth Sweep", target=lead_synth, parameter="cutoff_hz",
    points=[(0, 500), (6, 500), (10, 6000), (12, 800)],
)
song.automation(
    "Lead Echo Build", target=lead_echo, parameter="mix",
    points=[(0, 0.1), (6, 0.1), (10, 0.55), (12, 0.2)],
)
song.automation(
    "Lead Tone Outro", target=lead_tone, parameter="cutoff_hz",
    points=[(0, 5000), (10, 5000), (12, 400)], curve="linear",
)

print(song.validate())
pprint(song.configuration())
print(song.export_midi("renders/complete-song.mid"))
print(song.render("renders/complete-song.wav"))
```

Run, inspect, and listen:

Run the command Prism printed for your timestamped tutorial project.

Listen to `renders/complete-song.wav` inside the project folder.

This project demonstrates triggered samples, looping audio, one-shots, all
three drums, all three melodic instruments, all four waveforms, chords, rests, every synth control,
track and clip gain, panning, muting, explicit sections, an all-track section,
validation, configuration inspection, MIDI export, WAV rendering, and result
hashes. It also demonstrates an explicit stock instrument, an ordered
multi-effect chain, effects on a sample track, and three automation tracks.

All input and output paths are relative to `main.py`. Prism rejects absolute
paths, `..` traversal, missing sources, duplicate names, empty tracks, unknown
section tracks, unsafe output paths, and attempts to overwrite source files.

Checkpoint: this folder is a complete, copyable Prism project. Copy the folder,
install the Prism version recorded in `main.py`, and run that file again.
