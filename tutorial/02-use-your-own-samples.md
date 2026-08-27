# Level 2 — use your own samples

Goal: keep source sounds with the project and trigger a kick sample as a rhythm.

Prism reads WAV and AIFF files supported by libsndfile. Mono and stereo files
are accepted, and Prism resamples them to the project's sample rate.

## 1. Put a sample inside the project

Create the sounds folder if it does not exist:

```powershell
New-Item -ItemType Directory -Force .\tutorial-song\sounds | Out-Null
```

Copy a kick that you own. Replace the first path with its real location:

```powershell
Copy-Item "C:\Your Samples\kick.wav" .\tutorial-song\sounds\kick.wav
```

Keeping the sample under `tutorial-song\sounds` makes the project portable.
Prism deliberately rejects absolute paths such as `C:\Your Samples\kick.wav`
inside `main.py`.

## 2. Write the complete `main.py`

```python
from prism import Project


song = Project(
    __file__,
    "Sample Drum Loop",
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

```powershell
uv run python .\tutorial-song\main.py
Start-Process .\tutorial-song\renders\song.wav
```

## 4. Inspect reproducibility information

```powershell
Get-Content .\tutorial-song\.prism\project.json
```

Find `sounds/kick.wav` under `sources`. Its SHA-256 proves which exact kick file
was used. Replacing the sample and rerunning changes that hash and the render.

Checkpoint: the folder contains `main.py`, your kick, the rendered WAV, and a
machine-readable record tying them together.
