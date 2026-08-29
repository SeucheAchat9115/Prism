# Rendering and export

Prism builds the song at the `sample_rate` configured on `Project`. The
options on `render()` and `render_stems()` control the delivered WAV files and
do not change the readable song description.

## A practical final export

```python
result = song.render(
    "renders/song.wav",
    bit_depth=24,
    channels="stereo",
    sample_rate=48_000,
    tail_seconds=3,
)
```

The same options work for stems:

```python
stems = song.render_stems(
    "renders/stems",
    bit_depth=32,
    channels="stereo",
    sample_rate=48_000,
    tail_seconds=3,
)
```

## Bit depth

| Value | WAV storage | Good use |
| --- | --- | --- |
| `16` | PCM-16 | Listening copies and ordinary sharing |
| `24` | PCM-24 | Final masters and standard DAW exchange |
| `32` | 32-bit float | Stems and files that need extra headroom |

The default is 16-bit, preserving the behavior of existing projects. Prism
clips fixed-point output to the WAV range. A 32-bit floating-point export can
preserve samples above 0 dBFS so they can be reduced later without fixed-point
clipping. Float WAV metadata is normalized so repeated renders remain
byte-for-byte deterministic.

## Mono or stereo

`channels="stereo"` is the default. `channels="mono"` averages the left and
right channels evenly after the mix is complete. Panning therefore disappears
from a mono export. The selected channel layout applies to every stem as well
as the master.

## Output sample rate

Omit the render `sample_rate` to keep the project's sample rate. Set a value
from 8000 through 192000 Hz when another program or delivery format requires a
specific rate. Prism uses high-quality deterministic conversion after mixing.

The `sample_rate`, `frames`, `channels`, and `duration_seconds` fields in the
result describe the delivered file, not the internal render buffer.

## Effect and instrument tails

`tail_seconds` adds zero-input time after the final arrangement bar before
track, bus, and master effects are processed. This lets synthesizer releases,
feedback delays, and reverbs fade naturally through the real routing graph.
Normalization considers the complete song including its tail.

The default is zero seconds and the accepted range is 0 through 60 seconds.
Choose the shortest duration that lets the slowest effect become quiet. All
stems receive the same tail and remain exactly aligned.

Follow [Export quality and effect tails](../tutorial/18-export-quality-and-tails.md)
for a complete runnable project.
