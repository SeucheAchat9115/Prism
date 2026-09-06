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

Positions and durations are measured in quarter-note beats from the clip's
beginning, regardless of the project's written denominator. For example, a
one-bar 6/8 clip spans three quarter-note beats, so `Note("C4", 2.5, 0.25)`
starts half a quarter note before the end of that bar.

## Performance controls

`pitch_bend` supplies `(quarter_note, semitones)` points. Values are musical
semitones, not normalized MIDI values. `pitch_bend_range` declares the effective
range of the loaded patch (the default `2.0` preserves older projects). Prism
uses that declaration when it converts the curve to MIDI; it does not assume
that a VST3 patch uses ±2 semitones or silently send a plugin-specific range
setting. Verify the patch's range and declare it explicitly, for example
`pitch_bend_range=12` for a ±12-semitone patch.

`modulation` supplies `(quarter_note, amount)` points from 0 to 1. Both
controllers accept `pitch_bend_curve` or `modulation_curve` set to `"linear"`
or `"hold"`; the selected mode applies from each point until the next point.
`swing` delays every second subdivision, while seeded humanization adds
repeatable timing and velocity variation.

```python
lead = song.track("Lead").midi(
    notes,
    instrument=Uniwave.lead(),
    bars=1,
    pitch_bend=[(0, 0), (1, 0.7), (2, 0)],
    pitch_bend_range=2,
    pitch_bend_curve="linear",
    modulation=[(0, 0.1), (2, 0.8)],
    modulation_curve="hold",
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

## Arrangement boundaries and compiled events

Prism compiles each MIDI or drum track once before rendering or exporting it.
The stream contains stable note IDs, absolute quarter-note and sample-frame
positions, note-on/off events, controller curves, and every concrete repeated
or section-scoped clip boundary. Note-off events sort before a note-on at the
same timestamp, so overlapping notes with the same pitch remain distinct and a
retrigger is unambiguous.

Controller state resets to zero at each clip boundary by default. This prevents
a bent clip from leaving pitch bend active in a following unbent clip. Projects
that intentionally need a continuous controller can set
`Project(..., controller_boundary="retain")`; `"legacy"` omits synthetic
boundary/initial resets for projects that must preserve the old MIDI behavior.
The mode is explicit and is recorded in `song.configuration()`.

MIDI cannot carry an exact continuous ramp. Prism samples linear curves at no
more than 24 ticks (with the default 480 ticks per quarter note), includes all
authored points and boundaries, and then applies MIDI's 14-bit pitch-bend or
7-bit modulation quantization. The resulting timing error is at most half a
MIDI tick for a point's rounded timestamp; between emitted samples the curve is
approximated over at most 24 ticks. Quantization adds at most half a MIDI step:
`pitch_bend_range / (2 * 8191)` semitones for pitch bend and `1 / 254` of the
normalized modulation range. Native audio evaluates the same curve directly.
Agents can inspect the compiled source without rendering:

Standard MIDI channel note messages do not carry Prism's stable per-note IDs.
Native rendering preserves overlapping same-pitch voices independently, and
Prism emits each MIDI note-on/off pair in the defined order; a receiving device
may nevertheless apply its own same-pitch voice-stealing policy.

```python
from prism import compile_track_events

total_bars = sum(section.bars for section in song.sections)
compiled = compile_track_events(
    song,
    lead,
    total_bars=total_bars,
    total_frames=song.timing.bar_to_frame(total_bars),
)
print(compiled.notes[0].note_id, compiled.notes[0].on_frame)
print(compiled.boundaries)
```
