# MIDI and expressive notes

Prism offers two ways to write MIDI material.

## Step notation

Use a compact string when notes share a regular grid:

```python
bass = song.track("Bass").midi(
    "C2 - C2 Eb2 | G1 - Bb1 -",
    instrument=Uniwave.bass(),
    bars=2,
    velocity=104,
    gate=0.8,
)
```

Spaces separate steps, `-` is a rest, and `|` is a visual bar separator. Put
notes together with `+` for a chord.

## Individual notes

Use `Note` when timing, duration, or velocity differs per note:

```python
from prism import Note

notes = [
    Note("C4", start=0.0, duration=0.8, velocity=110),
    Note("Eb4", start=1.0, duration=0.45, velocity=92),
    Note("G4", start=1.75, duration=1.1, velocity=118),
]

lead = song.track("Lead").midi(notes, instrument=Uniwave.lead(), bars=1)
```

Positions and durations are measured in beats from the clip's beginning.

## Performance controls

`pitch_bend` supplies `(beat, semitones)` points from -2 to +2 semitones.
`modulation` supplies `(beat, amount)` points from 0 to 1. `swing` delays every
second subdivision, while seeded humanization adds repeatable timing and
velocity variation.

```python
lead = song.track("Lead").midi(
    notes,
    instrument=Uniwave.lead(),
    bars=1,
    pitch_bend=[(0, 0), (1, 0.7), (2, 0)],
    modulation=[(0, 0.1), (2, 0.8)],
    swing=0.58,
    humanize_timing_ms=8,
    humanize_velocity=5,
    humanize_seed=42,
)
```

The seed ensures another render receives exactly the same variation. See
[Expressive MIDI](../tutorial/14-expressive-midi.md) for a complete runnable
project and [the parameter reference](../tutorial/10-parameter-reference.md)
for every accepted range.
