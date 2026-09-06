# Level 22 — reuse a track-owned VST3 instrument

Goal: give one track one reproducible VST3 instrument configuration, then reuse
that patch across several clips without silently losing later declarations.

## 1. Declare the patch once

Register the plugin in the project first, then keep state and preset files inside
the project folder. Paths in `VST3(...)` are project-relative, so the resolved
configuration does not contain a machine-specific absolute path.

```python
from prism import Project, VST3


song = Project(
    "Track Owned VST Song",
    prism_version="0.2.0.dev0",
    tempo=124,
)

lead_patch = VST3(
    "surge",
    state="plugin-states/lead.state",
    parameters={"Cutoff": 0.35, "Resonance": 0.2},
)

lead = song.track("Lead", gain_db=-7).midi(
    "C4 Eb4 G4 Bb4",
    instrument=lead_patch,
    bars=1,
)

# Omitting instrument on a later clip reuses the track-owned declaration.
lead.midi("G4 F4 Eb4 C4", section="Chorus", bars=1)

song.section("Verse", bars=1, tracks=[lead])
song.section("Chorus", bars=1, tracks=[lead])

print(song.validate())
print(song.configuration()["tracks"][0]["instrument_specification"])
```

The first `midi(...)` call remains the convenient place to choose a VST3. The
track stores the complete immutable `VST3` declaration and gives it one stable
instrument instance identity. Equal declarations on later clips are accepted;
the track still owns only one specification and one public instrument object.

## 2. Change parameters over time with automation

Do not switch VST3 patches per clip. A timed parameter change is automation on
the track-owned instrument:

```python
instrument = lead.instrument_plugin
assert instrument is not None

song.automation(
    "Lead cutoff sweep",
    target=instrument,
    parameter="Cutoff",
    points=[(0.0, 0.35), (1.0, 0.75), (2.0, 0.45)],
)
```

Use the exact normalized parameter names exposed by the installed plugin. If a
different patch is needed at the same time, create a separate track and VST3
instance explicitly. This keeps an agent's edits inspectable and prevents one
clip from changing the sound of another clip by accident.

## 3. Replace the whole track deliberately

`track.instrument(...)` is the explicit whole-track replacement operation. It
updates every MIDI clip consistently and retains the stable track instance ID:

```python
lead.instrument(
    VST3(
        "surge",
        state="plugin-states/bright-lead.state",
        parameters={"Cutoff": 0.6, "Resonance": 0.15},
    )
)
```

Existing automation is rebound by parameter name when the new instrument can
accept it. If a lane would become orphaned or its values no longer fit the new
instrument's range, Prism rejects the replacement before changing the track;
remove or retarget that lane first.

## 4. Try the guarded failure

This declaration conflicts with the track-owned `Cutoff=0.35` configuration and
raises an actionable `ProjectError` before rendering:

```python
lead.midi(
    "Bb4",
    instrument=VST3("surge", parameters={"Cutoff": 0.8}),
)
```

The same rule applies to a different alias, state file, or preset file. Prism
does not create hidden per-clip VST instances to make such a conflict appear to
work.

[Back: use Serum on Windows →](21-serum-on-windows.md)
