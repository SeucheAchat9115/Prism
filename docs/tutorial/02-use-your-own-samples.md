# Level 2 — use your own samples

Goal: keep source sounds with the project and trigger a kick sample as a rhythm.

Prism reads WAV and AIFF files supported by libsndfile. Mono and stereo files
are accepted, and Prism resamples them to the project's sample rate.

## 1. Put a sample inside the project

Using your file manager, copy a kick that you own into the `sounds/` folder of
your timestamped tutorial project and name it `kick.wav`.

Keeping the sample under `sounds/` makes the project portable.
Prism deliberately rejects absolute paths such as `C:\Your Samples\kick.wav`
inside `main.py`.

## 2. Write the complete `main.py`

```python
from prism import Project


song = Project(
    "Sample Drum Loop",
    prism_version="0.2.0.dev0",
    tempo=112,
    sample_rate=44_100,
)

kick = song.track("Kick", gain_db=-2).sample(
    "sounds/kick.wav",
    "x--- x--- x-x- x---",
    bars=1,
)

hat = song.track("Hi-Hat", gain_db=-12, pan=0.2).drum(
    "hihat",
    "x-x- x-x- x-x- x-x-",
    seed=17,
)

song.section("Groove", bars=8, tracks=[kick, hat])

print(song.validate())
print(song.render("renders/song.wav"))
```

The one-bar kick and hi-hat parts repeat for the eight-bar section. Clip gain
belongs beside the sample or drum call; track gain and pan belong beside the
track name.

## 3. Render and listen

Run the exact command Prism printed when it created the tutorial project.

Open `renders/song.wav` inside that project folder.

## 4. Change the source sound

Replace `sounds/kick.wav` with a different kick and run the same command again.
The rhythm stays the same while the rendered sound changes.

Checkpoint: the folder contains `main.py`, your kick, and the rendered WAV.
