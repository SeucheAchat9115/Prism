# Mixing, routing, and automation

## Track processing

Track gain and pan are mixer controls. Effects process audio in authoring order:

```python
lead = song.track("Lead", gain_db=-7, pan=0.15).midi(
    "C4 Eb4 G4 Bb4",
    instrument=Uniwave.lead(),
)
filter_fx = lead.effect("filter", name="Lead Filter", cutoff_hz=5200)
lead.effect("delay", time_beats=0.5, feedback=0.3, mix=0.2)
```

Registered VST3 effects use the same ordered chain on tracks, buses, and the
master. Their parameters use normalized values from `0.0` to `1.0`; discover
the exact manufacturer-provided names with `prism plugins inspect`. See
[Use external VST3 plugins](external-vst3.md).

## Group buses and sends

A bus can be the main output for several tracks or a parallel return receiving
post-fader sends:

```python
drums = song.bus("Drums", tracks=[kick, snare, hat], gain_db=-1)
drums.effect("compressor", threshold_db=-16, ratio=3, attack_ms=10, release_ms=120)

reverb = song.bus("Reverb Return", gain_db=-8)
reverb.effect("reverb", room_size=0.7, damping=0.45, mix=1.0)
lead.send(reverb, gain_db=-12)
```

Master effects process the complete mix after tracks, buses, and returns:

```python
song.master_effect("compressor", threshold_db=-10, ratio=2)
```

## Automate plugin settings

Keep the plugin returned by `effect()` or access an instrument through
`track.instrument_plugin`, then target one numeric parameter:

```python
song.automation(
    "Open Lead Filter",
    target=filter_fx,
    parameter="cutoff_hz",
    points=[(0, 700), (4, 2400), (8, 9000)],
    curve="linear",
)
```

Point positions are absolute song bars. A `linear` curve moves continuously;
`hold` keeps the previous value until the next point. Prism validates each
value against the plugin's registered parameter range. Bars are converted
through the project's canonical timing map, so automation agrees with audio
and MIDI in meters such as 6/8 and 7/8 and does not drift after long sequences.

The compiled envelope has explicit boundaries: before the first point it holds
the plugin's configured base value, at a point it uses that point immediately,
between points it follows the selected curve, and after the last point it holds
the last value. This makes a late first point unambiguous:

```python
volume = lead.effect("gain", name="Volume", gain_db=-12)
song.automation(
    "Volume entry",
    target=volume,
    parameter="gain_db",
    points=[(0.5, -6), (2, 0)],
    curve="hold",
)
```

Existing scripts that intentionally relied on the old pre-first behavior can
declare `automation_compatibility="first_point_v0"` when constructing the
project. New projects use `initial_value_v1`; the policy is serialized in the
resolved configuration and is never inferred from `prism_version`. The legacy
mode is a migration aid, not a smoothing setting: an authored `hold` remains
an immediate step. Any smoothing applied to a future live controller is a
separate runtime concern and does not rewrite the authored envelope.

See [Plugins and automation](../tutorial/11-plugins-and-automation.md) and
[Buses, sends, and master effects](../tutorial/13-buses-sends-and-master-effects.md)
for complete projects.

## Export mixer channels as stems

When you want to continue in a DAW or share separate parts, add one line after
building the song:

```python
print(song.render_stems("renders/stems"))
```

Prism writes aligned stereo WAVs for every track, every group/return bus, and
the final master. Track files stop after the track controls; bus files include
their received routes and bus processing; the master includes the full final
chain. Individual stems keep their relative levels and are not normalized.

Track and bus files can represent two stages of the same sound. For example,
the Drum track files also feed the Drum Group file, so importing both stages
and playing them together doubles that material. Choose the stage you want.

Follow [Render stems](../tutorial/17-render-stems.md) for a complete project,
the returned generation path, and a tour of the generated folders.
