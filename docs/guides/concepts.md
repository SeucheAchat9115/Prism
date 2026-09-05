# How Prism thinks

A Prism song follows the same signal flow as a small recording session:

```text
Project
└── Section
    └── Track
        └── placed clip → instrument → effects → gain and pan
                                             ↓
                                  buses and sends
                                             ↓
                                      master effects
                                             ↓
                                         WAV file
```

## Project

`Project` holds global musical and technical settings: tempo, time signature,
sample rate, master gain, normalization, tracks, sections, routing, and
automation. Its sample library searches project-local audio without hiding the
resolved paths. The song's `main.py` creates exactly one project.

### One musical clock

Prism's canonical internal beat is one quarter note. A time signature describes
how many canonical beats are in a bar with this formula:

```text
quarter_notes_per_bar = numerator × 4 ÷ denominator
```

That means a bar lasts 4, 3, 3, and 3.5 quarter notes in 4/4, 3/4, 6/8, and
7/8 respectively. At 120 BPM those bars last 2, 1.5, 1.5, and 1.75 seconds.
The producer-facing `beats_per_bar` argument is the written numerator;
`beat_unit` is the written denominator. `Project.timing` exposes the resolved
[`MusicalTiming`](../reference/timing.md) conversion boundary.

`Note.start`, `Note.duration`, pitch-bend points, and modulation points use
quarter-note beats from their clip's beginning. A six-step pattern therefore
spans three quarter-note beats in one 6/8 bar, placing each step every half
beat. Automation points use absolute bar positions; the renderer converts each
absolute position to a sample-frame boundary once, so long arrangements do not
accumulate rounded one-bar errors.

Projects authored against Prism's old non-quarter-note behavior can opt into
the explicit compatibility mode when they need the old timing:

```python
song = Project(
    "Old Six Eight Project",
    prism_version="0.2.0.dev0",
    beats_per_bar=6,
    beat_unit=8,
    timing_compatibility="legacy_numerator_v0",
)
```

The default is `"quarter_note_v1"`; Prism never selects a timing convention
from the arbitrary `prism_version` label. To migrate such a project to the
canonical mode, remove the compatibility argument (or set it to
`"quarter_note_v1"`) and review explicit note/controller positions. If those
values represented written denominator-note steps under the old behavior,
scale them by `4 / beat_unit`; compact step notation is re-spaced from the
canonical clip length automatically.

## Track

A track is a named mixer channel. It has gain, pan, mute state, musical clips,
an instrument, and an ordered effect chain. Keep one kind of musical source on
each track—for example, one kick instrument or one Uniwave patch.

## Clip

A clip holds reusable musical material. It can be a drum pattern, MIDI notes,
a triggered sample pattern, or a complete audio file. Multiple placements on
one track provide section variations and fills.

## Instrument and effects

An instrument consumes MIDI or trigger events and creates sound. An effect
changes audio already created by an instrument. Effects run in the order they
are added to a track.

## Section

Sections arrange the song from left to right. A section has a name, length in
bars, and optionally an explicit list of tracks. Section-specific clips replace
a track's default clip in that section.

## Automation track

Automation changes one numeric plugin setting over the song timeline. Its
points use absolute bar positions and either linear movement or held steps.
Automation is separate from musical clips so the signal chain remains readable.

Continue with the [mini-song tutorial](../tutorial/04-build-a-mini-song.md) to
use all of these concepts in one project.
