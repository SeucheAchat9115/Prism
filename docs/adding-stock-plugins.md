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
track gain and pan → group/send buses → master effects
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

Create a new module such as `src/prism/stock_plugins/chorus.py`.

Declare the plugin definition in that module:

```python
definition = PluginDefinition(
    preset="chorus",
    kind="effect",
    parameters={
        "rate_hz": Parameter(0.8, 0.05, 10.0),
        "depth_ms": Parameter(6.0, 0.0, 30.0),
        "mix": Parameter(0.3, 0.0, 1.0),
    },
    defaults={"rate_hz": 0.8, "depth_ms": 6.0, "mix": 0.3},
    processor=process,
)
```

Import `Parameter` and `PluginDefinition` at the top of the module. The module
is the complete plugin implementation: its schema and processor travel
together.

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

### 2. Register the one-file plugin

Open `src/prism/stock_plugins/registry.py`, import the module, and add its
definition to `_EFFECTS`:

```python
from prism.stock_plugins import bass, chorus, delay, distortion, filter, gain, lead, pad

_EFFECTS = (
    gain.definition,
    filter.definition,
    distortion.definition,
    delay.definition,
    chorus.definition,
)
```

The registry is the only central file changed when a new plugin file is added.
It validates duplicate names and makes the plugin available to authoring,
rendering, automation, and configuration.

### 3. Implement deterministic audio processing

In the same plugin file, add a small processing function. Its inputs
should be the stereo sample buffer, parameter arrays, and only the project
values it genuinely needs:

```python
def process(
    samples: np.ndarray,
    parameters: Mapping[str, np.ndarray],
    sample_rate: int,
    tempo: float,
) -> np.ndarray:
    output = np.zeros_like(samples)
    # Deterministic DSP implementation goes here.
    return np.asarray(output, dtype=np.float64)
```

Parameter values are arrays with one value per audio frame. This is what makes
both static settings and automation use the same DSP path.

The registry passes parameter arrays to `process`; no change to the renderer
dispatch is needed. Keep dry/wet blending inside the plugin processor when the
effect has a `mix` parameter, so the plugin file remains self-contained.

### 4. Add effect tests

Add tests to `tests/test_plugins.py` that prove:

1. default settings render successfully;
2. every parameter boundary is accepted and an out-of-range value is rejected;
3. the effect changes a known input buffer;
4. swapping its order with another effect changes the result;
5. automating one parameter changes the expected song region;
6. rendering twice produces identical WAV bytes.

## Add a stock melodic instrument

The following example describes a hypothetical `pluck` instrument.

### 1. Create the plugin module

Create `src/prism/stock_plugins/pluck.py` with its defaults, `SynthPatch`,
parameters, and MIDI program:

```python
definition = PluginDefinition(
    preset="pluck",
    kind="instrument",
    parameters={
        "gain_db": Parameter(-6.0, -60.0, 12.0),
        "cutoff_hz": Parameter(4200.0, 20.0, 20_000.0),
    },
    defaults={"waveform": "triangle", "attack_ms": 2.0, "decay_ms": 180.0,
              "sustain": 0.2, "release_ms": 120.0, "cutoff_hz": 4200.0,
              "gain_db": -6.0},
    midi_program=45,
    melodic=True,
    synth_patch=SynthPatch("triangle", 2.0, 180.0, 0.2, 120.0, 4200.0, 0.55, 0.32),
)
```

Import `Parameter`, `PluginDefinition`, and `SynthPatch` in the module.

### 2. Register the module

Import `pluck` in `src/prism/stock_plugins/registry.py` and append
`pluck.definition` to the instrument registrations. A melodic definition with
`synth_patch` is automatically accepted by `midi()` and uses its `midi_program`
for MIDI export.

### 3. Define or extend synthesis behavior

If the new instrument uses the existing oscillator/envelope engine, its
`SynthPatch` is enough. A genuinely new synthesis algorithm should add a
processor callback to the definition and a small dispatch extension in the
engine; keep that callback in the plugin module.

### 4. Decide which settings can be automated

The plugin definition in `src/prism/stock_plugins/pluck.py` exposes
`gain_db` for every instrument and `cutoff_hz` for melodic instruments. Add a
new numeric setting there only when the renderer can apply it continuously.

An automated instrument parameter must use one value per frame and must not
change the timing or length of the MIDI clip. The standard engine currently
supports instrument `gain_db` and melodic `cutoff_hz` automation.

### 5. Add instrument tests

Cover these cases:

1. the new preset accepts MIDI notes and produces audible output;
2. default and custom parameters are visible in `song.configuration()`;
3. MIDI export uses the chosen program;
4. supported automation changes the sound over time;
5. two unchanged renders are byte-identical;
6. every documented parameter boundary is enforced.

## Add a stock percussion instrument

Create a module such as `src/prism/stock_plugins/tom.py` with a
`PluginDefinition(kind="instrument", drum_note=...)`, then import that module
and add its definition to the instrument registrations in
`src/prism/stock_plugins/registry.py`. The registry supplies the General MIDI
note and makes the preset available to `track.drum(...)` and `midi()`.

For a new generated drum sound, keep its deterministic hit processor in the
same plugin module and connect that processor through the definition. Noise-
based instruments must use a local NumPy random generator seeded from the
render specification; never use process-global random state. If the algorithm
needs a new engine callback, keep the callback implementation in the plugin
file and make only the minimal generic engine hook change.

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
