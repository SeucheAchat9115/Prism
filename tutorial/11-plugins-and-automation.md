# Level 11 — build a plugin chain and automate it

Goal: separate MIDI from its instrument, place several effects after that
instrument, and move plugin settings over the arranged song.

## 1. Understand the order

Prism reads each track from left to right:

```text
MIDI notes → Stock Lead → Drive → Echo → Final Filter → Track gain and pan
```

Calling `effect(...)` again adds the next effect. Changing the order changes
the sound.

## 2. Replace `main.py`

```python
from prism import Project


song = Project(
    "Automated Plugin Song",
    prism_version="0.2.0.dev0",
    tempo=112,
    master_gain_db=-4,
)

kick = song.track("Kick", gain_db=-3).drum(
    "kick",
    "x--- x--- x-x- x---",
)

lead = song.track("Lead", gain_db=-8, pan=0.15).midi(
    "C4 Eb4 G4 Bb4 | G4 F4 Eb4 -",
    bars=2,
    velocity=96,
    gate=0.8,
)

synth = lead.instrument(
    "lead",
    name="Stock Lead",
    waveform="saw",
    attack_ms=8,
    decay_ms=100,
    sustain=0.65,
    release_ms=160,
    cutoff_hz=900,
    gain_db=-6,
)

lead.effect("distortion", name="Drive", drive_db=8, mix=0.2)

echo = lead.effect(
    "delay",
    name="Echo",
    time_beats=0.5,
    feedback=0.32,
    mix=0.05,
)

tone = lead.effect(
    "filter",
    name="Final Tone",
    cutoff_hz=5000,
    mix=1,
)

song.section("Intro", bars=2, tracks=[lead])
song.section("Beat", bars=2, tracks=[kick, lead])
song.section("Build", bars=2, tracks=[kick, lead])
song.section("Outro", bars=2, tracks=[lead])

song.automation(
    "Synth Sweep",
    target=synth,
    parameter="cutoff_hz",
    points=[(0, 300), (4, 1200), (6, 6000), (8, 800)],
)

song.automation(
    "Echo Build",
    target=echo,
    parameter="mix",
    points=[(0, 0.05), (4, 0.1), (6, 0.55), (8, 0.2)],
)

song.automation(
    "Outro Tone",
    target=tone,
    parameter="cutoff_hz",
    points=[(0, 5000), (6, 5000), (8, 400)],
)

print(song.validate())
print(song.export_midi("renders/song.mid"))
print(song.render("renders/song.wav"))
```

## 3. Run and listen

Run the command Prism printed for your timestamped tutorial project. Open
`renders/song.wav` inside that folder.

Listen for the lead becoming brighter through the Build, the echo becoming
stronger around bar 6, and the final filter closing during the Outro.

## 4. Try stepped automation

Change the Echo Build lane to:

```python
song.automation(
    "Echo Build",
    target=echo,
    parameter="mix",
    points=[(0, 0.05), (4, 0.35), (6, 0.7)],
    curve="hold",
)
```

`linear` moves smoothly between points. `hold` keeps each value until the next
point, producing an immediate change there.

Checkpoint: you can identify the MIDI part, instrument plugin, ordered effect
chain, and three independent automation tracks in one readable project file.
