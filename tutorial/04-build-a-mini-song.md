# Level 4 — build a complete mini-song

Goal: combine six tracks into an Intro, Verse, Chorus, and Outro. This level is
self-contained and uses no external samples.

## 1. Write the complete `main.py`

```python
from prism import Project


song = Project(
    "Night Window",
    prism_version="0.2.0.dev0",
    tempo=120,
    sample_rate=44_100,
    master_gain_db=-3,
)

kick = song.track("Kick", gain_db=-3).drum(
    "kick",
    "x--- x--- x--- x---",
)

snare = song.track("Snare", gain_db=-7).drum(
    "snare",
    "---- x--- ---- x---",
    seed=11,
)

hat = song.track("Hi-Hat", gain_db=-12, pan=0.25).drum(
    "hihat",
    "x-x- x-x- x-x- x-x-",
    seed=17,
)

bass = song.track("Bass", gain_db=-6, pan=-0.12).midi(
    "C2 - C2 Eb2 | G1 - Bb1 -",
    instrument="bass",
    bars=2,
)

pad = song.track("Pad", gain_db=-11, pan=-0.3).midi(
    "C3+Eb3+G3 - | Ab2+C3+Eb3 -",
    instrument="pad",
    bars=2,
    velocity=80,
)

lead = song.track("Lead", gain_db=-9, pan=0.3).midi(
    "G4 Bb4 C5 - | G4 F4 Eb4 -",
    instrument="lead",
    bars=2,
    velocity=95,
)

song.section("Intro", bars=2, tracks=[hat, pad])
song.section("Verse", bars=2, tracks=[kick, snare, hat, bass])
song.section("Chorus", bars=2)  # no track list means every track
song.section("Outro", bars=2, tracks=[kick, hat, pad])

print(song.validate())
print(song.export_midi("renders/night-window.mid"))
print(song.render("renders/song.wav"))
```

Track variables make the arrangement readable and typo-resistant. A section
with no `tracks=` list plays every track. Sections are appended in playback
order, so the Python file reads like the song from top to bottom.

## 2. Render the eight-bar song

Run the command Prism printed for your timestamped tutorial project.

Open `renders/song.wav` inside the project folder.

At 120 BPM in 4/4, eight bars last sixteen seconds.

Checkpoint: the project is now a small linear production with rhythm, bass,
harmony, melody, arrangement, stereo mix, WAV, and MIDI.
