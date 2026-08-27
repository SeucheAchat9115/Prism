# Level 13 — mix with buses, sends, and master effects

Goal: compress several drum tracks together, share one reverb between tracks,
and process the finished mix through a master effect.

## 1. Understand the three routes

```text
Kick + Snare + Hi-Hat → Drum Bus → Master
Snare ──send──────────→ Room Bus → Master
Lead ───send──────────→ Room Bus → Master
All master inputs → Master Effects → WAV
```

A group bus replaces the tracks' direct route. A send is an additional copy,
so the dry track remains audible. Master effects process the complete mix.

## 2. Replace `main.py`

```python
from prism import Project


song = Project(
    "Shared Mixer",
    prism_version="0.2.0.dev0",
    tempo=116,
    master_gain_db=-6,
)

kick = song.track("Kick", gain_db=-4).drum("kick", "x--- x--- x--- x---")
snare = song.track("Snare", gain_db=-8).drum(
    "snare", "---- x--- ---- x---", seed=11
)
hat = song.track("Hi-Hat", gain_db=-13, pan=0.25).drum(
    "hihat", "x-x- x-x- x-x- x-x-", seed=17
)
bass = song.track("Bass", gain_db=-7, pan=-0.1).midi(
    "C2 - C2 Eb2 | G1 - Bb1 -", instrument="bass", bars=2
)
lead = song.track("Lead", gain_db=-10, pan=0.15).midi(
    "C4 Eb4 G4 Bb4 | G4 F4 Eb4 -", bars=2
)

drums = song.bus("Drum Bus", tracks=[kick, snare, hat], gain_db=-1)
drum_glue = drums.effect(
    "compressor", name="Drum Glue", threshold_db=-18, ratio=3,
    attack_ms=12, release_ms=120, makeup_db=2,
)

room = song.bus("Room Return", gain_db=-7)
room_reverb = room.effect(
    "reverb", name="Shared Room", room_size=0.6, damping=0.4, width=1, mix=1
)
snare.send(room, gain_db=-10)
lead.send(room, gain_db=-14)

song.master_effect(
    "compressor", name="Master Control", threshold_db=-8, ratio=2,
    attack_ms=20, release_ms=180, makeup_db=1,
)

song.section("Intro", bars=2, tracks=[hat, bass])
song.section("Full Mix", bars=4, tracks=[kick, snare, hat, bass, lead])
song.section("Outro", bars=2, tracks=[bass, lead])

song.automation(
    "Drum Glue Build", target=drum_glue, parameter="mix",
    points=[(0, 0.4), (2, 0.7), (6, 1.0)],
)
song.automation(
    "Room Build", target=room_reverb, parameter="room_size",
    points=[(0, 0.35), (4, 0.6), (8, 0.8)],
)

print(song.validate())
print(song.export_midi("renders/song.mid"))
print(song.render("renders/song.wav"))
```

## 3. Run and listen

Run the tutorial project's printed command and open `renders/song.wav`.

Listen for the three drums breathing together through one compressor. The
snare and lead should share the same room character while keeping their dry
signals. The final compressor should gently control the complete mix.

## 4. Hear each routing layer

Try these changes separately and render after each one:

1. Set `muted=True` on `Drum Bus` to hear that grouped drums no longer route
   directly to the master.
2. Change both send gains to `-60` to remove nearly all shared reverb.
3. Change the Room Return gain from `-7` to `-2` to make the room louder.
4. Comment out `song.master_effect(...)` to compare the unprocessed mix.

Checkpoint: you can distinguish a track effect, group bus, parallel return,
send level, bus effect, and master effect in one reproducible project file.
