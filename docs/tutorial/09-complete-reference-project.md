# Level 9 — complete Prism reference project

Goal: use every producer-facing authoring feature in one readable project.

Using your file manager, put `kick.wav` and `percussion-loop.wav` into the
project's `sounds/` folder. Create a `recordings/` folder beside it and put
`vocal-shot.wav` there.

Replace the project’s `main.py` with this complete reference:

```python
from pprint import pprint

from prism import Note, Project, SynthWave, Uniwave


song = Project(
    "Complete Prism Song",
    prism_version="0.2.0.dev0",
    tempo=112,
    sample_rate=44100,
    beats_per_bar=4,
    beat_unit=4,
    master_gain_db=-4,
    normalize=True,
)
song.samples.add_folder("recordings")

sample_kick = song.track("Sample Kick", gain_db=-2).sample(
    "kick.wav", "x--- x--- x--- x---", bars=1, gain_db=-1
)
built_in_kick = song.track("Built-In Kick", gain_db=-5).drum(
    "kick", "x--- x--- x-x- x---"
)
built_in_kick.drum(
    "kick", "x--- x-x- x--- xxxx", section="Chorus", start_bar=0
)
loop = song.track("Percussion Loop", gain_db=-8, pan=-0.1).audio(
    "percussion-loop.wav", bars=2, loop=True, gain_db=-2
)
vocal = song.track("Vocal One-Shot", gain_db=-7, pan=0.25).audio(
    "vocal-shot.wav", bars=2, loop=False
)
snare = song.track("Snare", gain_db=-8).drum(
    "snare", "---- x--- ---- x---", seed=11
)
hat = song.track("Hi-Hat", gain_db=-13, pan=0.3).drum(
    "hihat", "x-x- x-x- x-x- x-x-", seed=17
)
bass = song.track("Bass", gain_db=-6, pan=-0.15).midi(
    "C2 - C2 Eb2 | G1 - Bb1 -",
    instrument=Uniwave.bass(), bars=2, velocity=105, gate=0.78, gain_db=-4,
)
pad = song.track("Pad", gain_db=-12, pan=-0.3).midi(
    "C3+Eb3+G3 - | Ab2+C3+Eb3 -",
    instrument=Uniwave.pad(), bars=2, velocity=85, gate=0.92, gain_db=-6,
)
lead = song.track("Lead", gain_db=-10, pan=0.35).midi(
    "C4 D4 Eb4 G4 | Bb4 G4 Eb4 -",
    bars=2, velocity=96, gate=0.82,
)
lead.midi(
    [
        Note("G4", start=0, duration=0.75, velocity=88),
        Note("Bb4", start=1.5, duration=0.4, velocity=106),
        Note("C5", start=2, duration=1.25, velocity=118),
    ],
    section="Chorus", pitch_bend=[(0, 0), (1, 2), (2, 0)],
    modulation=[(0, 0), (2, 1), (4, 0)], swing=0.62,
    humanize_timing_ms=6, humanize_velocity=4, humanize_seed=42,
)
lead_synth = lead.instrument(
    Uniwave(
        waves=(
            SynthWave("sine", level=0.15, octave=-1),
            SynthWave("triangle", level=0.25, phase=0.25),
            SynthWave("saw", level=0.7, detune_cents=-7),
            SynthWave("square", level=0.35, detune_cents=7),
        ),
        attack_ms=8, decay_ms=90, sustain=0.62, release_ms=140,
        cutoff_hz=3600, resonance=0.22, drive=0.14,
        vibrato_rate_hz=5.2, vibrato_depth_cents=8,
        noise_level=0.02, noise_seed=19,
    ),
    name="Uniwave Lead", gain_db=-6,
)
lead.effect("distortion", name="Lead Drive", drive_db=8, mix=0.2)
lead_echo = lead.effect(
    "delay", name="Lead Echo", time_beats=0.5, feedback=0.3, mix=0.1
)
lead_tone = lead.effect("filter", name="Lead Tone", cutoff_hz=5000, mix=1)
sample_kick.effect("gain", name="Kick Trim", gain_db=-1)
drums = song.bus("Drum Bus", tracks=[built_in_kick, snare, hat], gain_db=-1)
drum_glue = drums.effect(
    "compressor", name="Drum Glue", threshold_db=-18, ratio=3, makeup_db=2
)
room = song.bus("Room Return", gain_db=-7)
room_reverb = room.effect("reverb", name="Shared Room", room_size=0.6, mix=1)
lead.send(room, gain_db=-14)
vocal.send(room, gain_db=-10)
song.master_effect("compressor", name="Master Control", threshold_db=-8, ratio=2)
muted_idea = song.track("Muted Sine Idea", muted=True).midi(
    "C5 - G4 -", instrument=Uniwave(waves=(SynthWave("sine"),))
)

song.section("Intro", bars=2, tracks=[built_in_kick, loop, pad])
song.section("Verse", bars=4, tracks=[sample_kick, snare, hat, loop, bass, pad])
song.section("Chorus", bars=4)
song.section("Outro", bars=2, tracks=[vocal, pad, lead, muted_idea])

song.automation(
    "Lead Synth Sweep", target=lead_synth, parameter="cutoff_hz",
    points=[(0, 500), (6, 500), (10, 6000), (12, 800)],
)
song.automation(
    "Lead Echo Build", target=lead_echo, parameter="mix",
    points=[(0, 0.1), (6, 0.1), (10, 0.55), (12, 0.2)],
)
song.automation(
    "Lead Tone Outro", target=lead_tone, parameter="cutoff_hz",
    points=[(0, 5000), (10, 5000), (12, 400)], curve="linear",
)
song.automation(
    "Drum Bus Blend", target=drum_glue, parameter="mix",
    points=[(0, 0.5), (6, 0.8), (12, 1.0)],
)
song.automation(
    "Room Size", target=room_reverb, parameter="room_size",
    points=[(0, 0.35), (6, 0.6), (12, 0.8)],
)

print(song.validate())
print(song.samples.files())
pprint(song.configuration())
print(song.export_midi("renders/complete-song.mid"))
print(song.render(
    "renders/complete-song.wav", bit_depth=24, channels="stereo",
    sample_rate=48000, tail_seconds=3,
))
print(song.render_stems(
    "renders/stems", bit_depth=32, channels="stereo",
    sample_rate=48000, tail_seconds=3,
))
```

Run, inspect, and listen:

Run the command Prism printed for your timestamped tutorial project.

Listen to `renders/complete-song.wav` inside the project folder.

This project demonstrates triggered samples, looping audio, one-shots, all
three drums, three Uniwave sound designs, all four waveforms, chords, rests,
every Uniwave synth control,
track and clip gain, panning, muting, explicit sections, an all-track section,
validation, configuration inspection, MIDI export, WAV rendering, and result
hashes. It also demonstrates an explicit stock instrument, an ordered
multi-effect chain, effects on a sample track, and several automation tracks.
Its audio sources use the default sample library, an additional registered
folder, short filename lookup, and a printable file inventory.
It also includes a section-specific clip, drum group bus, shared reverb send,
bus automation, final master processing, individually positioned MIDI notes,
pitch bend, modulation, swing, and deterministic humanization.
The final call also exports aligned track, bus/return, and master stems.
Both WAV exports choose their delivery quality and retain three seconds for
synthesizer releases, delays, and reverbs to finish.

All input and output paths are relative to `main.py`. Prism rejects absolute
paths, `..` traversal, missing sources, duplicate names, empty tracks, unknown
section tracks, unsafe output paths, and attempts to overwrite source files.

Checkpoint: this folder is a complete, copyable Prism project. Copy the folder,
install the Prism version recorded in `main.py`, and run that file again.
