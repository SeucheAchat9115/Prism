# Samples, loops, and audio editing

Put source WAV or AIFF files in the project's `sounds/` folder. Prism supports
triggered one-shots and complete audio clips.

## Trigger a sample as a rhythm

```python
song.track("Kick").sample(
    "sounds/kick.wav",
    "x--- x--- x--- x---",
    bars=1,
)
```

## Play a loop or one-shot

```python
song.track("Texture").audio(
    "sounds/texture.wav",
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
