"""Uniwave, Prism's configurable multi-wave native synthesizer plugin."""

import math
from dataclasses import asdict

import numpy as np

from prism.music import ControlPoint, Note, note_frequency
from prism.plugins import Parameter, PluginDefinition
from prism.synthesis.types import NativeSynthSpec, SynthWave, Uniwave


def settings(sound: Uniwave) -> dict[str, object]:
    """Return readable, serializable Uniwave settings."""

    return {
        "waves": [asdict(wave) for wave in sound.waves],
        "attack_ms": sound.attack_ms,
        "decay_ms": sound.decay_ms,
        "sustain": sound.sustain,
        "release_ms": sound.release_ms,
        "cutoff_hz": sound.cutoff_hz,
        "resonance": sound.resonance,
        "drive": sound.drive,
        "vibrato_rate_hz": sound.vibrato_rate_hz,
        "vibrato_depth_cents": sound.vibrato_depth_cents,
        "noise_level": sound.noise_level,
        "noise_seed": sound.noise_seed,
        "gain_db": -6.0,
    }


def render(
    spec: NativeSynthSpec,
    sample_rate: int,
    tempo_bpm: float,
    beats_per_bar: int,
) -> np.ndarray:
    """Render Uniwave oscillators, envelopes, controllers, filter, and drive."""

    sound = spec.uniwave or Uniwave()
    seconds = spec.bars * beats_per_bar * 60.0 / tempo_bpm
    frames = max(1, int(round(seconds * sample_rate)))
    frames_per_beat = sample_rate * 60.0 / tempo_bpm
    output = np.zeros(frames, dtype=np.float64)
    bends = _control_values(spec.pitch_bend, frames, frames_per_beat)
    modulation = _control_values(spec.modulation, frames, frames_per_beat)
    events = spec.note_events or _step_events(spec, beats_per_bar)
    wave_level = max(1.0, sum(wave.level for wave in sound.waves))

    for event_index, note in enumerate(events):
        start = int(round(note.start * frames_per_beat))
        if start >= frames:
            continue
        note_frames = max(1, int(round(note.duration * frames_per_beat)))
        release = max(0, int(round(sound.release_ms * sample_rate / 1_000.0)))
        voice_frames = min(frames - start, note_frames + release)
        positions = np.arange(voice_frames, dtype=np.float64)
        global_time = (start + positions) / sample_rate
        mod_depth = sound.vibrato_depth_cents + 50.0 * modulation[start : start + voice_frames]
        vibrato = mod_depth * np.sin(2.0 * np.pi * sound.vibrato_rate_hz * global_time)
        expression_cents = 100.0 * bends[start : start + voice_frames] + vibrato
        voice = np.zeros(voice_frames, dtype=np.float64)
        base_frequency = note_frequency(note.pitch)
        for wave in sound.waves:
            tuning = 1_200 * wave.octave + 100 * wave.semitones + wave.detune_cents
            frequency = base_frequency * np.power(
                2.0, (tuning + expression_cents) / 1_200.0
            )
            phase = np.cumsum(frequency) / sample_rate
            phase -= phase[0]
            phase += wave.phase
            voice += wave.level * _oscillator(wave, phase)
        voice /= wave_level
        if sound.noise_level > 0.0:
            generator = np.random.default_rng(sound.noise_seed + event_index)
            voice += sound.noise_level * generator.uniform(-1.0, 1.0, voice_frames)
        envelope = _envelope(
            voice_frames,
            note_frames=note_frames,
            sample_rate=sample_rate,
            sound=sound,
        )
        output[start : start + voice_frames] += (
            0.38 * (note.velocity / 100.0) * voice * envelope
        )

    output = _filter(output, sound.cutoff_hz, sound.resonance, sample_rate)
    drive_gain = 1.0 + sound.drive * 10.0
    if drive_gain > 1.0:
        output = np.tanh(output * drive_gain) / math.tanh(drive_gain)
    return np.asarray(output, dtype=np.float64)


def _step_events(spec: NativeSynthSpec, beats_per_bar: int) -> tuple[Note, ...]:
    clip_beats = spec.bars * beats_per_bar
    step = clip_beats / len(spec.sequence)
    gate = 0.8 if spec.gate is None else spec.gate
    return tuple(
        Note(pitch, index * step, step * gate, 100)
        for index, token in enumerate(spec.sequence)
        if token != "-"
        for pitch in token.split("+")
    )


def _control_values(
    points: tuple[ControlPoint, ...], frames: int, frames_per_beat: float
) -> np.ndarray:
    if not points:
        return np.zeros(frames, dtype=np.float64)
    positions = [point.beat * frames_per_beat for point in points]
    values = [point.value for point in points]
    if positions[0] > 0.0:
        positions.insert(0, 0.0)
        values.insert(0, 0.0)
    return np.asarray(
        np.interp(np.arange(frames, dtype=np.float64), positions, values),
        dtype=np.float64,
    )


def _oscillator(wave: SynthWave, phase: np.ndarray) -> np.ndarray:
    if wave.waveform == "sine":
        return np.sin(2.0 * np.pi * phase)
    if wave.waveform == "triangle":
        return 2.0 * np.abs(2.0 * (phase - np.floor(phase + 0.5))) - 1.0
    if wave.waveform == "saw":
        return 2.0 * (phase - np.floor(phase + 0.5))
    return np.where(np.sin(2.0 * np.pi * phase) >= 0.0, 1.0, -1.0)


def _envelope(
    frames: int,
    *,
    note_frames: int,
    sample_rate: int,
    sound: Uniwave,
) -> np.ndarray:
    attack = max(0, int(round(sound.attack_ms * sample_rate / 1_000.0)))
    decay = max(0, int(round(sound.decay_ms * sample_rate / 1_000.0)))
    release = max(0, int(round(sound.release_ms * sample_rate / 1_000.0)))
    envelope = np.full(frames, sound.sustain, dtype=np.float64)
    attack_end = min(frames, attack)
    if attack_end:
        envelope[:attack_end] = np.linspace(0.0, 1.0, attack_end, endpoint=False)
    decay_end = min(frames, attack_end + decay)
    if decay_end > attack_end:
        envelope[attack_end:decay_end] = np.linspace(
            1.0, sound.sustain, decay_end - attack_end, endpoint=False
        )
    note_off = min(frames, note_frames)
    if note_off < frames:
        release_end = min(frames, note_off + release)
        start_level = envelope[max(0, note_off - 1)]
        if release_end > note_off:
            envelope[note_off:release_end] = np.linspace(
                start_level, 0.0, release_end - note_off, endpoint=False
            )
        envelope[release_end:] = 0.0
    return envelope


def _filter(
    samples: np.ndarray, cutoff_hz: float, resonance: float, sample_rate: int
) -> np.ndarray:
    cutoff = min(cutoff_hz, sample_rate * 0.45)
    alpha = 1.0 - math.exp(-2.0 * math.pi * cutoff / sample_rate)
    first = 0.0
    second = 0.0
    output = np.empty_like(samples)
    for index, sample in enumerate(samples):
        first += alpha * (sample - first)
        second += alpha * (first - second)
        output[index] = second + resonance * 2.0 * (first - second)
    return np.asarray(output, dtype=np.float64)


_DEFAULT = Uniwave()

definition = PluginDefinition(
    preset="uniwave",
    kind="instrument",
    parameters={
        "gain_db": Parameter(-6.0, -60.0, 12.0),
        "cutoff_hz": Parameter(_DEFAULT.cutoff_hz, 20.0, 20_000.0),
    },
    defaults=settings(_DEFAULT),
    midi_program=81,
    melodic=True,
    synth_processor=render,
)
