# Level 7 — use audio loops and one-shots

Goal: learn `audio(...)`, which places a complete audio file on a track instead
of triggering it from a rhythm pattern.

Copy two audio files into the project. Use material you own or have permission
to use:

```powershell
Copy-Item C:\path\to\your\percussion-loop.wav .\tutorial-song\sounds\percussion-loop.wav
Copy-Item C:\path\to\your\vocal-shot.wav .\tutorial-song\sounds\vocal-shot.wav
```

Replace `tutorial-song\main.py` with:

```python
from prism import Project


song = Project(__file__, "Audio Files", tempo=120)

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
    instrument="bass",
    bars=2,
)

song.section("Loop Only", bars=2, tracks=[loop, bass])
song.section("With One-Shot", bars=2, tracks=[loop, vocal, bass])

print(song.validate())
print(song.render("renders/song.wav"))
```

Run and listen:

```powershell
uv run python .\tutorial-song\main.py
Start-Process .\tutorial-song\renders\song.wav
```

`loop=True` repeats or trims the complete source to the declared clip length.
`loop=False` plays it once and pads the remaining clip with silence. The clip
itself loops again when a section is longer than its `bars=` value. Prism
accepts mono or stereo WAV/AIFF files and resamples them to the project sample
rate automatically.

Checkpoint: the vocal begins again only when its two-bar part cycles, while the
percussion source fills its complete two-bar part.
