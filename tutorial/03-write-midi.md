# Level 3 — write MIDI and synthesizer parts

Goal: describe pitched notes and chords, render them with built-in instruments,
and export a standard MIDI file.

## 1. Learn the short notation

- `C4` is middle C.
- `F#3` and `Bb2` are valid accidentals.
- `-` is a rest.
- `C3+Eb3+G3` is a chord in one step.
- Spaces, commas, and `|` separate steps; `|` is only visual grouping.

Every step has equal duration inside the clip's number of bars.

## 2. Write the complete `main.py`

```python
from prism import Project


song = Project("MIDI Sketch", prism_version="0.2.0.dev0", tempo=108)

bass = song.track("Bass", gain_db=-6, pan=-0.1).midi(
    "C2 - C2 Eb2 | G1 - Bb1 -",
    instrument="bass",
    bars=2,
    velocity=105,
)

pad = song.track("Pad", gain_db=-11, pan=-0.25).midi(
    "C3+Eb3+G3 - | Ab2+C3+Eb3 -",
    instrument="pad",
    bars=2,
    velocity=82,
)

lead = song.track("Lead", gain_db=-9, pan=0.3).midi(
    "G4 Bb4 C5 - | G4 F4 Eb4 -",
    instrument="lead",
    bars=2,
    velocity=96,
)

song.section("Chords", bars=2, tracks=[bass, pad])
song.section("Melody", bars=4, tracks=[bass, pad, lead])

print(song.validate())
print(song.export_midi("renders/song.mid"))
print(song.render("renders/song.wav"))
```

`midi(...)` is both musical data and a renderable Prism part. The `instrument`
selects a deterministic built-in sound for the WAV. The same arranged notes go
into the `.mid` file for use in another DAW.

## 3. Run, listen, and locate the MIDI file

Run the command Prism printed for your timestamped tutorial project.

Listen to `renders/song.wav` inside the project. The MIDI file is beside it at
`renders/song.mid`.

Sample/audio-only tracks are not guessed into MIDI. Built-in kick, snare, and
hi-hat parts are exported as General MIDI percussion; pitched tracks use
programs appropriate to bass, lead, and pad.

Checkpoint: one readable note sequence now creates both an audible WAV and a
portable MIDI arrangement.
