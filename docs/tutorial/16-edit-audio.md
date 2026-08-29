# Level 16 — edit loops and samples

Goal: turn ordinary WAV or AIFF files into flexible Prism parts. Put two audio
files that you own in the project’s `sounds/` folder: `drum-loop.wav` and
`texture.wav`.

Replace `main.py` with this complete project:

```python
from prism import Project


song = Project(
    "Edited Audio",
    prism_version="0.2.0.dev0",
    tempo=120,
    master_gain_db=-5,
)

loop = song.track("Drum Loop", gain_db=-4).audio(
    "sounds/drum-loop.wav",
    bars=4,
    loop=True,
    start_seconds=0.25,
    end_seconds=8.25,
    fade_in_ms=12,
    fade_out_ms=40,
    playback_rate=0.98,
    stretch_bars=4,
)

reverse_texture = song.track("Reverse Texture", gain_db=-10, pan=0.3).audio(
    "sounds/texture.wav",
    bars=4,
    loop=False,
    start_seconds=1.0,
    end_seconds=5.0,
    reverse=True,
    playback_rate=0.75,
    transpose_semitones=-5,
    fade_in_ms=250,
    fade_out_ms=500,
    stretch_bars=4,
)

hits = song.track("Sample Hits", gain_db=-7).sample(
    "sounds/texture.wav",
    "x--- --x- x--- ---x",
    bars=1,
    start_seconds=0.4,
    end_seconds=0.65,
    fade_in_ms=4,
    fade_out_ms=70,
    reverse=False,
    playback_rate=1.2,
    transpose_semitones=12,
)

song.section("Edited Loop", bars=4, tracks=[loop, reverse_texture, hits])

print(song.validate())
print(song.render("renders/song.wav"))
```

Run the command printed when you created the tutorial project, then listen to
`renders/song.wav`.

`start_seconds` and `end_seconds` select a source region before any other edit.
`reverse` flips that region. `playback_rate` changes speed, while
`transpose_semitones` changes pitch in semitones. Positive transposition makes
the source faster as a natural sampler-style pitch shift. `stretch_bars` then
resizes the edited source to an exact musical length before `audio(...)` loops
or pads it to its `bars=` value.

Fades are measured in milliseconds and are applied to each prepared source.
That keeps loop boundaries smooth and makes repeated sample hits clean.

Try these changes one at a time:

1. Set `reverse=False` on the texture and compare its direction.
2. Change `stretch_bars=2` while keeping `bars=4`; the loop repeats twice.
3. Set `playback_rate=1.5` and `transpose_semitones=0` for a faster texture.
4. Remove `end_seconds` to use the rest of the source.

Checkpoint: every source edit is stored in `configuration()` and rendered
deterministically, so the same project folder always produces the same WAV.
