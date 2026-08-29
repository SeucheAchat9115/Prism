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
automation. The song's `main.py` creates exactly one project.

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
