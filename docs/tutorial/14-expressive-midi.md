# Level 14 — perform expressive MIDI

Goal: place notes freely, give each note its own length and velocity, bend
pitch, add modulation, swing the groove, and humanize it reproducibly.

## 1. Read one expressive note

```text
Note("C4", start=0.5, duration=0.75, velocity=96)
```

All positions and durations are measured in quarter-note beats from the
beginning of the clip. This note begins halfway through beat one and lasts
three quarters of a beat. Unlike compact note strings, notes do not need to sit
on equal steps, and the unit does not change when the written meter uses eighth
or half notes.

## 2. Replace `main.py`

```python
from prism import Note, Project, Uniwave


song = Project(
    "Expressive MIDI",
    prism_version="0.2.0.dev0",
    tempo=108,
    master_gain_db=-6,
)

kick = song.track("Kick", gain_db=-4).drum(
    "kick", "x--- x--- x--- x---", bars=2
)
snare = song.track("Snare", gain_db=-9).drum(
    "snare", "---- x--- ---- x---", bars=2, seed=11
)

bass = song.track("Human Bass", gain_db=-7, pan=-0.1).midi(
    [
        Note("C2", start=0.0, duration=0.8, velocity=105),
        Note("C2", start=1.5, duration=0.35, velocity=82),
        Note("Eb2", start=2.0, duration=1.25, velocity=112),
        Note("G1", start=4.0, duration=0.7, velocity=100),
        Note("Bb1", start=5.5, duration=0.4, velocity=88),
        Note("C2", start=6.5, duration=1.2, velocity=116),
    ],
    instrument=Uniwave.bass(),
    bars=2,
    swing=0.64,
    humanize_timing_ms=7,
    humanize_velocity=4,
    humanize_seed=42,
)
bass.effect("compressor", threshold_db=-20, ratio=3, makeup_db=2)

lead = song.track("Bending Lead", gain_db=-10, pan=0.2).midi(
    [
        Note("G4", start=0.0, duration=1.5, velocity=92),
        Note("Bb4", start=2.0, duration=1.0, velocity=108),
        Note("C5", start=3.5, duration=2.0, velocity=118),
        Note("G4", start=6.0, duration=1.5, velocity=86),
    ],
    instrument=Uniwave.lead(),
    bars=2,
    pitch_bend=[(0, 0), (1, 2), (2, 0), (4, -2), (5, 0)],
    modulation=[(0, 0), (3, 0.25), (5, 1), (8, 0)],
)
lead.effect("delay", time_beats=0.5, feedback=0.3, mix=0.2)
lead.effect("reverb", room_size=0.55, mix=0.18)

song.section("Groove", bars=4, tracks=[kick, snare, bass])
song.section("Lead", bars=4, tracks=[kick, snare, bass, lead])

print(song.validate())
print(song.export_midi("renders/song.mid"))
print(song.render("renders/song.wav"))
```

## 3. Run and listen

Run the command printed for the tutorial project, then open `renders/song.wav`.

Listen for the bass notes starting between the obvious grid positions and
hitting at different strengths. The lead bends upward, returns to pitch, bends
downward, and gains vibrato as the modulation value rises.

The same timing and velocity variation returns on every render because
`humanize_seed=42` is part of `main.py`.

## 4. Change the feel

Try one change at a time:

1. Set `swing=0.5` for straight timing, then compare it with `0.64`.
2. Set both humanize amounts to zero for a completely fixed performance.
3. Change `humanize_seed` to obtain a different reproducible performance.
4. Change the lead's `2` semitone bend to `1` for a smaller bend.
5. Move a `Note` by changing only its `start` value.

Checkpoint: every performed note and controller movement is explicit, editable,
exportable to MIDI, audible in the WAV, and reproducible from the project file.
