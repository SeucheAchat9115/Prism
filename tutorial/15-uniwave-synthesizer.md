# Level 15 — design sounds with Uniwave

Goal: build a bass, chord, and lead sound with Prism's native synthesizer.

Uniwave is the default synth for MIDI tracks. A `SynthWave` is one oscillator.
Each oscillator can use its own waveform, volume, octave, semitone tuning,
fine detuning, and starting phase. A `Uniwave` combines one to four of them and
shapes the combined sound with an envelope, filter, drive, noise, and vibrato.

Replace your project’s `main.py` with this complete song:

```python
from prism import Project, SynthWave, Uniwave


song = Project(
    "Uniwave Sound Lab",
    prism_version="0.2.0.dev0",
    tempo=118,
    master_gain_db=-5,
)

bass_sound = Uniwave(
    waves=(
        SynthWave("saw", level=0.8),
        SynthWave("square", level=0.3, octave=-1, detune_cents=4),
    ),
    attack_ms=4,
    decay_ms=120,
    sustain=0.55,
    release_ms=100,
    cutoff_hz=950,
    resonance=0.3,
    drive=0.22,
)

chord_sound = Uniwave(
    waves=(
        SynthWave("triangle", level=0.7, detune_cents=-6),
        SynthWave("triangle", level=0.7, detune_cents=6, phase=0.25),
        SynthWave("sine", level=0.25, octave=1),
    ),
    attack_ms=180,
    decay_ms=350,
    sustain=0.72,
    release_ms=500,
    cutoff_hz=2800,
    resonance=0.12,
    vibrato_rate_hz=4.2,
    vibrato_depth_cents=5,
)

lead_sound = Uniwave(
    waves=(
        SynthWave("saw", level=0.65, detune_cents=-8),
        SynthWave("saw", level=0.65, detune_cents=8),
        SynthWave("square", level=0.18, semitones=12, phase=0.5),
    ),
    attack_ms=8,
    decay_ms=130,
    sustain=0.62,
    release_ms=220,
    cutoff_hz=5200,
    resonance=0.2,
    drive=0.14,
    vibrato_rate_hz=5.5,
    vibrato_depth_cents=9,
    noise_level=0.025,
    noise_seed=23,
)

kick = song.track("Kick", gain_db=-5).drum("kick", "x--- x--- x--- x---")
bass = song.track("Bass", gain_db=-6).midi(
    "C2 - C2 Eb2 | G1 - Bb1 -", bars=2, instrument=bass_sound
)
chords = song.track("Chords", gain_db=-12, pan=-0.2).midi(
    "C3+Eb3+G3 - | Bb2+D3+F3 -", bars=2, instrument=chord_sound
)
lead = song.track("Lead", gain_db=-10, pan=0.25).midi(
    "G4 Bb4 C5 G4 | F4 Eb4 D4 -", bars=2, instrument=lead_sound
)
lead.effect("delay", time_beats=0.5, feedback=0.25, mix=0.16)

song.section("Uniwave Loop", bars=2, tracks=[kick, bass, chords, lead])

print(song.validate())
print(song.render("renders/song.wav"))
```

Run the command Prism printed when it created your tutorial project, then
listen to `renders/song.wav`.

## Start simple

For quick results, use `Uniwave.bass()`, `Uniwave.lead()`, or `Uniwave.pad()`.
These return complete sounds that you can use directly:

```python
bass = song.track("Bass").midi("C2 - G1 -", instrument=Uniwave.bass())
```

Use the longer form when you want to design the sound yourself. Try one change
at a time, render again, and listen:

1. Change a wave from `"saw"` to `"sine"`, `"triangle"`, or `"square"`.
2. Set one wave to `octave=-1` for weight or `octave=1` for brightness.
3. Move `cutoff_hz` lower for darkness and higher for brightness.
4. Increase `resonance` to emphasize the filter edge.
5. Increase `attack_ms` for a slower fade-in or `release_ms` for a longer tail.
6. Add gentle `drive`, `noise_level`, or `vibrato_depth_cents` for character.

Checkpoint: you have built three independent polyphonic Uniwave instruments.
Chords create several voices at once, while every note uses all configured
waves. The same `noise_seed` always produces the same render.
