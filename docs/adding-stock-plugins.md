# Adding a stock plugin to Prism

This guide is for contributors who want to add a built-in instrument or effect.
A stock plugin ships with Prism, renders offline without audio hardware, and can
be used directly from a producer’s `main.py`.

## Start with the signal flow

Every track follows this order:

```text
MIDI notes or trigger events
        ↓
stock instrument
        ↓
effect 1 → effect 2 → effect 3
        ↓
track gain and pan
        ↓
song mix
```

An instrument consumes musical events and creates audio. An effect receives
audio from the instrument or previous effect and returns processed audio.
Automation is separate song data that supplies changing parameter values to a
plugin during rendering.

## Design rules for every stock plugin

A stock plugin must be:

- deterministic: the same project must produce the same sample values;
- offline: rendering must not require an audio device or real-time clock;
- project-local: it must not read unrelated files, settings, or credentials;
- bounded: every numeric parameter needs a documented minimum and maximum;
- automatable where practical: numeric effect settings are automation targets;
- readable: producer-facing names use musical language and explicit units;
- tested: cover validation, audible processing, ordering, automation, and
  deterministic rerendering.

Use these parameter suffixes consistently:

- `_db` for decibels;
- `_hz` for frequencies;
- `_ms` for milliseconds;
- `_beats` for tempo-relative durations;
- `mix` for a dry/wet value from `0.0` through `1.0`.

Use `float64` NumPy arrays while processing. Return the same number of stereo
frames you received. Do not modify another track’s buffer.

## Add a stock effect

The following example describes a hypothetical `chorus` effect.

### 1. Declare its public name and parameters

Open `src/prism/plugins.py`.

Add the preset to `EffectPreset`:

```python
EffectPreset = Literal["gain", "filter", "distortion", "delay", "chorus"]
```

Add one entry to `_EFFECT_PARAMETERS`:

```python
"chorus": {
    "rate_hz": Parameter(0.8, 0.05, 10.0),
    "depth_ms": Parameter(6.0, 0.0, 30.0),
    "mix": Parameter(0.3, 0.0, 1.0),
},
```

Each `Parameter` receives `default`, `minimum`, and `maximum`. Prism uses this
schema to reject unknown settings and out-of-range values. Every declared
effect parameter automatically becomes available to `song.automation(...)`.

The producer-facing call will be:

```python
chorus = lead.effect(
    "chorus",
    name="Wide Chorus",
    rate_hz=0.8,
    depth_ms=6,
    mix=0.3,
)
```

### 2. Implement deterministic audio processing

Open `src/prism/effects.py` and add a small processing function. Its inputs
should be the stereo sample buffer, parameter arrays, and only the project
values it genuinely needs:

```python
def _chorus(
    samples: np.ndarray,
    *,
    rate_hz: np.ndarray,
    depth_ms: np.ndarray,
    sample_rate: int,
) -> np.ndarray:
    output = np.zeros_like(samples)
    # Deterministic DSP implementation goes here.
    return np.asarray(output, dtype=np.float64)
```

Parameter values are arrays with one value per audio frame. This is what makes
both static settings and automation use the same DSP path.

Add an explicit `chorus` branch inside `process_track_plugins(...)`, before the
final delay branch:

```python
elif effect.preset == "chorus":
    wet = _chorus(
        output,
        rate_hz=parameters["rate_hz"],
        depth_ms=parameters["depth_ms"],
        sample_rate=project.sample_rate,
    )
    output = _blend(output, wet, parameters["mix"])
```

Keep dry/wet blending outside the processor when possible. That gives all
effects the same `mix=0` and `mix=1` behavior.

### 3. Add effect tests

Add tests to `tests/test_plugins.py` that prove:

1. default settings render successfully;
2. every parameter boundary is accepted and an out-of-range value is rejected;
3. the effect changes a known input buffer;
4. swapping its order with another effect changes the result;
5. automating one parameter changes the expected song region;
6. rendering twice produces identical WAV bytes.

## Add a stock melodic instrument

The following example describes a hypothetical `pluck` instrument.

### 1. Register the preset type

Open `src/prism/synthesis/types.py` and add `pluck` to `SynthPreset` and
`MELODIC_PRESETS`:

```python
SynthPreset = Literal[
    "kick", "snare", "hihat", "bass", "lead", "pad", "pluck"
]

MELODIC_PRESETS = frozenset({"bass", "lead", "pad", "pluck"})
```

Update the melodic instrument `Literal` annotations and validation messages in
`src/prism/project/builder.py`. This keeps editor autocomplete and producer
errors synchronized with the registry.

### 2. Define the default patch

Open `src/prism/synthesis/engine.py` and add a `_Patch` entry:

```python
"pluck": _Patch(
    waveform="triangle",
    attack_ms=2.0,
    decay_ms=180.0,
    sustain_level=0.2,
    release_ms=120.0,
    cutoff_hz=4200.0,
    gate=0.55,
    amplitude=0.32,
),
```

Add `pluck` to the accepted preset annotation of
`native_instrument_settings(...)`. That function is the single bridge between
the synthesis defaults and the public plugin description, so defaults shown by
`song.configuration()` stay identical to those used for rendering.

If the instrument uses the existing oscillator and envelope engine, this patch
entry is normally the only synthesis change. If it needs a new synthesis
algorithm, give that algorithm a dedicated function and select it explicitly
inside `_render_melodic(...)`.

### 3. Add the MIDI program mapping

Open `src/prism/midi.py` and add a General MIDI program to `_PROGRAMS`:

```python
_PROGRAMS = {"bass": 38, "lead": 81, "pad": 89, "pluck": 45}
```

This affects exported `.mid` playback only. Prism’s WAV render continues to use
the stock instrument implementation.

### 4. Decide which settings can be automated

`instrument_plugin(...)` in `src/prism/plugins.py` currently exposes
`gain_db` for every instrument and `cutoff_hz` for melodic instruments. Add a
new numeric setting there only when the renderer can apply it continuously.

Then update `_instrument_automation(...)` in `src/prism/effects.py`. An
automated instrument parameter must use one value per frame and must not change
the timing or length of the MIDI clip.

### 5. Add instrument tests

Cover these cases:

1. the new preset accepts MIDI notes and produces audible output;
2. default and custom parameters are visible in `song.configuration()`;
3. MIDI export uses the chosen program;
4. supported automation changes the sound over time;
5. two unchanged renders are byte-identical;
6. every documented parameter boundary is enforced.

## Add a stock percussion instrument

Percussion presets also belong in `SynthPreset` and `PERCUSSION_PRESETS` in
`src/prism/synthesis/types.py`. Add the generated hit in
`_render_percussion(...)`, register its General MIDI note in `_DRUM_NOTES` in
`src/prism/midi.py`, and update the accepted drum preset annotation and message
in `src/prism/project/builder.py`.

Noise-based instruments must use `spec.seed` through the local NumPy random
generator. Never use process-global random state.

## Update the producer documentation

For either plugin kind:

1. add exact defaults and ranges to `tutorial/10-parameter-reference.md`;
2. add a complete musical example to the appropriate tutorial level;
3. update the functionality map in `tutorial/README.md`;
4. mention the new stock preset in `README.md` when it changes the basic
   producer workflow.

Examples should remain complete `main.py` files that run from the repository
root. Use musical parameter names and let the CLI-generated project retain its
literal `prism_version`.

## Run the complete checks

From the Prism repository root:

```text
uv sync --locked --extra dev
uv run pytest --cov=prism --cov-report=term-missing
uv run mypy src/prism
uv run ruff check .
uv build --no-sources
```

Before submitting the change, also create a tutorial project, paste in the new
example, render it twice, listen to the WAV, and confirm that the two reported
SHA-256 values match.

## Review checklist

- The plugin has one clear musical purpose.
- Parameter names include units and have bounded ranges.
- Static values and automated values share the same processing path.
- Effect ordering is observable and documented.
- MIDI export remains valid for new instruments.
- DSP is deterministic and preserves stereo frame count.
- Producer errors name the plugin and invalid setting.
- Reference documentation and a complete example are included.
- Tests, typing, linting, coverage, and package building pass.
