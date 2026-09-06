# Level 7 — use audio loops and one-shots

Goal: learn `audio(...)`, which places a complete audio file on a track instead
of triggering it from a rhythm pattern.

Using your file manager, copy two audio files that you own into the project’s
`sounds/` folder. Name them `percussion-loop.wav` and `vocal-shot.wav`.

Replace the project’s `main.py` with:

```python
from prism import Project, Uniwave


song = Project("Audio Files", prism_version="0.2.0.dev0", tempo=120)

loop = song.track("Percussion Loop", gain_db=-7).audio(
    "sounds/percussion-loop.wav",
    bars=2,
    loop=True,
    gain_db=-2,
)

vocal = song.track("Vocal Shot", gain_db=-5, pan=0.25).audio(
    "sounds/vocal-shot.wav",
    bars=2,
    loop=False,
)

bass = song.track("Bass", gain_db=-7, pan=-0.15).midi(
    "C2 - C2 - | G1 - Bb1 -",
    instrument=Uniwave.bass(),
    bars=2,
)

song.section("Loop Only", bars=2, tracks=[loop, bass])
song.section("With One-Shot", bars=2, tracks=[loop, vocal, bass])

print(song.validate())
print(song.render("renders/song.wav"))
```

Run and listen:

Run the command Prism printed for your timestamped tutorial project.

Open `renders/song.wav` inside the project folder.

`loop=True` repeats or trims the complete source inside this placement.
`loop=False` plays the source once. The separate placement option
`repeat=True` repeats the placement when its active section is longer than its
`bars=` value; `loop=False, repeat=False` therefore gives one one-shot at one
timeline position. A natural one-shot can release past its placement or
section boundary when the export has enough tail. Use
`release_policy="cut"` when the arrangement should deliberately stop it at
that boundary.

Prism accepts mono or stereo WAV/AIFF files and resamples them to the project
sample rate automatically. A track can become inactive in the next section
without cutting a natural release; use `audio_release_policy="cut"` on the
project or `release_policy="cut"` on the placement for an intentional cut.

Checkpoint: the vocal begins again only when its two-bar part cycles, while the
percussion source fills its complete two-bar part.
