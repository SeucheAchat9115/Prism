# Level 19: Find and organize samples

In this level you organize audio into several folders and use readable short
filenames in `main.py`. Prism finds unique names for you and stops with clear
choices when two samples have the same name.

## 1. Add your audio files

Using your file manager, create these folders inside the tutorial project and
copy in three audio files that you own:

```text
sounds/
└── drums/
    ├── kick-heavy.wav
    └── snare-dry.wav
recordings/
└── atmosphere.wav
```

The names matter for this tutorial, but the audio content can be anything.

## 2. Ask Prism what it can see

From the Prism repository root, run this with your real timestamped folder:

```text
uv run prism samples "projects/tutorial-20260829-120000"
```

Prism lists the three relative paths. It does not run `main.py` and it ignores
generated WAV files under `renders/`.

## 3. Replace `main.py`

Replace everything in the tutorial project's `main.py` with this:

```python
from prism import Project

song = Project(
    "Organized Samples",
    prism_version="0.2.0.dev0",
    tempo=112,
)

song.samples.add_folder("recordings")

kick = song.track("Kick", gain_db=-3).sample(
    "kick-heavy.wav",
    "x--- x--- x--- x---",
)
snare = song.track("Snare", gain_db=-7).sample(
    "snare-dry.wav",
    "---- x--- ---- x---",
)
atmosphere = song.track("Atmosphere", gain_db=-14).audio(
    "atmosphere.wav",
    bars=2,
    loop=True,
    fade_in_ms=100,
    fade_out_ms=200,
)

song.section("Sample Loop", bars=2, tracks=[kick, snare, atmosphere])

print("Available samples:", song.samples.files())
print(song.render("renders/song.wav"))
```

## 4. Run and listen

Run the usual command for the tutorial project and listen to
`renders/song.wav`. Although `main.py` uses only filenames, the project remains
fully reproducible: Prism stores the resolved project-relative paths in its
configuration.

`sounds/` is searched automatically, including all its subfolders. The
`recordings/` folder becomes searchable because of this line:

```python
song.samples.add_folder("recordings")
```

## 5. See duplicate protection

Copy another file named `kick-heavy.wav` into `sounds/other/` and run the
project again. Prism refuses to guess and shows both matching paths. Resolve
the ambiguity by changing the Kick track to an explicit path:

```python
"sounds/drums/kick-heavy.wav",
```

Run `uv run prism samples "projects/your-project-folder"` again to see the
duplicate warning before rendering.

## 6. Try a typo

Change `"snare-dry.wav"` to `"snre-dry.wav"`. Prism suggests the closest
available filename with `Did you mean 'snare-dry.wav'?`. Restore the correct
spelling when finished.

Checkpoint: you can organize large sample collections without filling the
song file with repetitive paths, while ambiguous names remain explicit and
reproducible.
