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

## Explicit delivery profiles

For repeatable delivery, use a serializable `ExportProfile`. It separates the
project's internal render rate from the rate written to disk and gives the
export a named contract that can be stored with a render job:

```python
from prism import ExportProfile

master_profile = ExportProfile(
    name="24-bit-master",
    bit_depth=24,
    channels="stereo",
    delivery_sample_rate=48_000,
    normalization="peak",
    normalization_target_dbfs=-1.0,
    clipping="error",
)
master = song.render("renders/master.wav", profile=master_profile)
```

When a profile is supplied, it is the complete delivery contract and takes
precedence over the legacy `bit_depth`, `channels`, `sample_rate`, and
`tail_seconds` keywords. Without a profile, those keywords continue to work;
`Project(normalize=True)` is adapted to peak normalization at -1 dBFS, while
fixed-point output keeps the historical clipping behavior.

`normalization="peak"` is peak normalization only. It measures the signal
after downmixing and sample-rate conversion, then applies the requested dBFS
target before fixed-point quantization. Prism does not claim LUFS or other
loudness normalization. Use `normalization="none"` when the source level
must be preserved.

Fixed-point profiles support three explicit clipping policies:

| Policy | Behavior |
| --- | --- |
| `"error"` | Fail when delivery-domain samples exceed the fixed-point range |
| `"warn"` | Emit a warning and clip those samples |
| `"clip"` | Clip without a warning |

32-bit float delivery preserves headroom above 0 dBFS; its diagnostics still
report overloads, but it does not fixed-point clip them. The result's
`diagnostics` records `peak_before_normalization`, `preclip_peak`,
`overload_samples`, and `clipped_samples`.

Optional TPDF dither is applied once immediately before integer WAV
quantization. It is seeded for repeatability and never applied to float WAVs:

```python
master_profile = ExportProfile(
    name="dithered-listening-copy",
    bit_depth=16,
    dither="tpdf",
    dither_seed=20260906,
    clipping="warn",
)
song.render("renders/listening.wav", profile=master_profile)
```

For stems, set `dither_stems=True` to apply the same seeded policy to each
stem, and `normalize_stems=True` only when independently peak-normalized
stems are deliberately wanted. Otherwise only the master follows the
profile's peak-normalization setting, preserving the existing aligned stem
behavior.

Stem delivery mode is a separate choice from file format. The default
`stem_mode="channel_taps"` exports every post-track and post-bus tap for
mixer inspection. For a production delivery set, use
`stem_mode="master_inputs"`:

```python
stems = song.render_stems(
    "renders/production-stems",
    profile=ExportProfile(
        name="production-stems",
        bit_depth=32,
        normalization="none",
    ),
    stem_mode="master_inputs",
)
```

This mode exports ungrouped track outputs plus group and return bus outputs. A
track routed into a group is omitted because its signal is already present in
that bus, so importing the whole set does not double the group. The stem
metadata labels these files `pre_master` and declares the reconstruction target
as the pre-master mix before master gain, master effects, and final delivery
normalization. The `master.wav` in the same generation is the finished
reference, so it does not require rerunning plugins separately. Sum the
pre-master stems before integer quantization to reconstruct that target; a
nonlinear compressor or limiter on the master cannot be recreated by running
each stem through that processor independently. Independent stem normalization
is rejected in this production mode.

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

## Native arrangement ranges and release automation

The 256-bar limit applies to an authored clip, not to the song. Native MIDI
clips retain that limit so an accidental clip declaration cannot allocate an
unbounded implicit buffer. During arrangement rendering, Prism compiles the
absolute note/event range and supplies the complete output frame range
separately. A song can therefore contain a 256-bar section followed by another
bar without turning the complete arrangement into a 257-bar clip.

Uniwave `release_ms` automation is sampled once at the note-off frame. The
sampled value determines that voice's release duration; changing the lane after
note-off affects later notes, but does not resize an already active release.
A constant automated release is therefore equivalent to the same static
Uniwave envelope. The explicit render range remains a hard endpoint: a natural
release is rendered only when the requested arrangement plus `tail_seconds`
contains enough frames. Prism does not silently allocate beyond that range.

## Stem output ownership and recovery

`render_stems("renders/stems")` treats the argument as a producer-facing
container, not as a directory to sweep. Prism stores each completed export in
`renders/stems/.prism-stems/generations/` and returns that generation path as
`StemRenderResult.directory`. The versioned
`.prism-stems/manifest.json` records the WAV files generated by the last
successful export.

Prism stages every WAV before publishing the manifest. If a later write fails,
the previous manifest and completed generation remain current. After a
successful export, Prism removes only unchanged files recorded by the previous
manifest. Modified generated files, producer-added files, unrelated WAVs, and
legacy `tracks`/`buses` files are preserved. The manifest replacement is
recoverable on Windows and Linux; Prism does not claim that publishing a set
of files is one atomic multi-file transaction.

Output paths are protected against source recordings, project scripts, VST
states/presets, the VST registry, symlink escapes, and other registered project
files. Choose a separate output container such as `renders/stems/` rather than
`sounds/` or `plugin-states/`.

Follow [Export quality and effect tails](../tutorial/18-export-quality-and-tails.md)
for a complete runnable project.
