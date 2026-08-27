# Level 12 — arrange clips, variations, and fills

Goal: keep one instrument on each track while giving sections their own
patterns and placing one-time fills at exact bars.

## 1. Understand default and section clips

A clip without `section=...` is the track's default. It plays in every active
section that has no clips written especially for that section.

As soon as a track has a clip for `section="Chorus"`, those Chorus clips replace
the default there. `start_bar` is counted from the start of that section, and
`repeat=False` plays the clip only once.

## 2. Replace `main.py`

```python
from prism import Project, Uniwave


song = Project(
    "Clips and Fills",
    prism_version="0.2.0.dev0",
    tempo=110,
    master_gain_db=-5,
)

kick = song.track("Kick", gain_db=-3)
kick.drum("kick", "x--- x--- x--- x---")
kick.drum("kick", "x--- x--- x--- x---", section="Verse")
kick.drum("kick", "x--- x-x- x--- x-x-", section="Chorus")
kick.drum(
    "kick",
    "xxxx xxxx xxxx xxxx",
    section="Verse",
    start_bar=3,
    repeat=False,
)

snare = song.track("Snare", gain_db=-8)
snare.drum("snare", "---- x--- ---- x---")
snare.drum("snare", "---- x--- --x- x-x-", section="Chorus")

bass = song.track("Bass", gain_db=-7).midi(
    "C2 - C2 Eb2 | G1 - Bb1 -",
    instrument=Uniwave.bass(),
    bars=2,
)
bass.midi(
    "Ab1 - Bb1 C2 | Eb2 - G2 -",
    instrument=Uniwave.bass(),
    bars=2,
    section="Chorus",
)
bass.effect("compressor", threshold_db=-20, ratio=4, makeup_db=2)

lead = song.track("Lead", gain_db=-10, pan=0.2).midi(
    "C4 Eb4 G4 - | Bb4 G4 Eb4 -",
    instrument=Uniwave.lead(),
    bars=2,
    section="Chorus",
)
lead.effect("delay", time_beats=0.5, feedback=0.3, mix=0.2)
lead.effect("reverb", room_size=0.6, mix=0.2)

song.section("Intro", bars=2, tracks=[bass])
song.section("Verse", bars=4, tracks=[kick, snare, bass])
song.section("Chorus", bars=4, tracks=[kick, snare, bass, lead])
song.section("Outro", bars=2, tracks=[kick, bass])

print(song.validate())
print(song.export_midi("renders/song.mid"))
print(song.render("renders/song.wav"))
```

## 3. Run and listen

Run the command printed when the tutorial project was created. Open
`renders/song.wav` and listen for:

- the default bass in the Intro, Verse, and Outro;
- the Verse kick fill beginning at Verse bar 3;
- the replacement kick, snare, and bass clips in the Chorus;
- the Lead appearing only because its only clip belongs to the Chorus.

## 4. Move the fill

Change the kick fill from `start_bar=3` to `start_bar=2.5`, render again, and
listen for it beginning halfway through the third bar of the Verse.

Checkpoint: one track can now contain a reusable default clip, section-specific
variations, and precisely positioned one-time clips without duplicating its
instrument or effect chain.
