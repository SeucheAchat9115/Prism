# Level 17: Render stems

In this level you make a short mixed song, render the normal master, and also
export every mixer channel as an aligned WAV file. Stems are useful when you
want to continue mixing in a DAW, share separate parts with another producer,
or process one channel elsewhere.

## 1. Replace `main.py`

Replace everything in your tutorial project's `main.py` with this:

```python
from prism import Project, Uniwave

song = Project(
    "Stem Export",
    prism_version="0.2.0.dev0",
    tempo=120,
)

kick = song.track("Kick", gain_db=-4).drum(
    "kick", "x--- x--- x--- x---"
)
snare = song.track("Snare", gain_db=-7).drum(
    "snare", "---- x--- ---- x---"
)
bass = song.track("Bass", gain_db=-7).midi(
    "C2 - C2 Eb2 | G1 - Bb1 -",
    instrument=Uniwave.bass(),
    bars=2,
)
lead = song.track("Lead", gain_db=-9, pan=0.15).midi(
    "G4 Bb4 C5 - | G4 F4 Eb4 -",
    instrument=Uniwave.lead(),
    bars=2,
)

drums = song.bus("Drum Group", tracks=[kick, snare], gain_db=-1)
drums.effect("compressor", threshold_db=-18, ratio=3, makeup_db=1)

room = song.bus("Room Return", gain_db=-8)
room.effect("reverb", room_size=0.65, damping=0.4, mix=1)
snare.send(room, gain_db=-10)
lead.send(room, gain_db=-14)

song.master_effect("compressor", threshold_db=-10, ratio=2)
song.section("Mini Song", bars=2)

print(song.render("renders/song.wav"))
print(song.render_stems("renders/stems"))
```

## 2. Run and listen

Run the command Prism printed when it created your tutorial project. First
listen to `renders/song.wav`. This is the finished master you already know.

Now open `renders/stems/`. Prism created:

```text
stems/
├── tracks/
│   ├── 01-kick.wav
│   ├── 02-snare.wav
│   ├── 03-bass.wav
│   └── 04-lead.wav
├── buses/
│   ├── 01-drum-group.wav
│   └── 02-room-return.wav
└── master.wav
```

Play a track stem by itself to hear that channel. Play the room return to hear
only the shared reverb. `master.wav` is exactly the same finished audio as
`song.wav`.

## 3. Understand what is included

Every file is stereo, has the complete song length, and starts at bar 0. This
means you can drag all desired stems to the same starting point in a DAW and
they remain synchronized.

- A track stem includes that track's sound, effects, gain, and pan.
- A bus stem includes tracks routed or sent to it, followed by its effects,
  gain, and pan.
- The master includes the complete route, master effects, master gain, and
  normalizing.

Track and bus stems show different stages of the same mixer. Do not combine a
track with the group bus that already contains it unless you intentionally
want to double that sound. Prism does not normalize individual stems, so their
levels stay useful relative to one another.

## 4. Try a change

Change `lead.send(room, gain_db=-14)` to `gain_db=-6`, run the file again, and
compare `buses/02-room-return.wav`. Prism safely replaces its generated WAV
files and removes obsolete WAVs from the `tracks` and `buses` stem folders.

Checkpoint: you can now export a finished master and aligned channel stems
from the same reproducible `main.py`.
