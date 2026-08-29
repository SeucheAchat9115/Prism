# Samples, loops, and audio editing

Put source WAV, AIFF, FLAC, or OGG files in the project's `sounds/` folder.
Prism searches that folder and its subfolders automatically, so a unique
filename is enough:

## Trigger a sample as a rhythm

```python
song.track("Kick").sample(
    "kick.wav",
    "x--- x--- x--- x---",
    bars=1,
)
```

## Play a loop or one-shot

```python
song.track("Texture").audio(
    "texture.wav",
    bars=4,
    loop=True,
)
```

With `loop=True`, Prism repeats the prepared source through the clip. With
`loop=False`, it plays once and leaves silence afterward.

## Prepare the source before placement

Both `sample()` and `audio()` support the same deterministic editing stages:

1. Select `start_seconds` through `end_seconds`.
2. Reverse the selected source when `reverse=True`.
3. Apply `playback_rate` and `transpose_semitones`.
4. Optionally resize to `stretch_bars`.
5. Apply `fade_in_ms` and `fade_out_ms`.
6. Loop or fit the result into its placement.

```python
song.track("Edited Loop").audio(
    "sounds/loop.wav",
    bars=4,
    start_seconds=1.2,
    end_seconds=5.8,
    fade_in_ms=20,
    fade_out_ms=80,
    reverse=False,
    playback_rate=1.0,
    transpose_semitones=-2,
    stretch_bars=4,
)
```

Playback rate changes speed and pitch together. Transposition adds an
independent pitch/speed ratio. Stretching then forces the prepared region to an
exact musical duration. See [Edit audio](../tutorial/16-edit-audio.md) for the
complete listening exercise.

## Organize samples into folders

Subfolders beneath `sounds/` need no setup:

```text
sounds/
├── drums/kick-heavy.wav
├── drums/snare-dry.wav
└── textures/rain.flac
```

You can still write `"kick-heavy.wav"` when that filename is unique. Register
other project-local folders when they fit your project better:

```python
song.samples.add_folder("recordings")
vocal = song.track("Vocal").audio("vocal-take-3.wav", loop=False)
```

Use `song.samples.files()` to inspect registered folders from Python. Use an
explicit path such as `"sounds/acoustic/kick.wav"` when two files share a
name. Prism reports every matching path instead of choosing unpredictably.

## List project audio from the terminal

From the repository root, run:

```text
uv run prism samples "projects/my-song-20260829-120000"
```

The command lists audio anywhere in the project, ignores generated files under
`renders/`, and highlights duplicate filenames. It reads the folders directly
without executing `main.py`.

See [Find and organize samples](../tutorial/19-find-and-organize-samples.md)
for a complete project example.
