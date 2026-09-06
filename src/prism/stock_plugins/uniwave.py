"""Uniwave, Prism's configurable multi-wave native synthesizer plugin."""

from dataclasses import asdict
from typing import Mapping

import numpy as np

from prism.music import ControlPoint, Note, control_values, db_gain, note_frequency
from prism.plugins import Parameter, PluginDefinition
from prism.stock_plugins.gain import db_envelope
from prism.synthesis.types import NativeSynthSpec, SynthWave, Uniwave
from prism.timing import MusicalTiming


def settings(sound: Uniwave) -> dict[str, object]:
    """Return readable, serializable Uniwave settings."""

    resolved: dict[str, object] = {
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
    for index, wave in enumerate(sound.waves, start=1):
        resolved[f"wave_{index}_level"] = wave.level
        resolved[f"wave_{index}_detune_cents"] = wave.detune_cents
    return resolved


def render(
    spec: NativeSynthSpec,
    sample_rate: int,
    tempo_bpm: float,
    quarter_notes_per_bar: float,
) -> np.ndarray:
    """Render Uniwave oscillators, envelopes, controllers, filter, and drive."""

    sound = spec.uniwave or Uniwave()
    automation = spec.automation or {}
    timing = MusicalTiming(tempo_bpm=tempo_bpm, sample_rate=sample_rate)
    total_quarter_notes = spec.bars * quarter_notes_per_bar
    frames = spec.frame_count or max(1, timing.quarter_notes_to_frame(total_quarter_notes))
    output = np.zeros(frames, dtype=np.float64)
    bends = _control_values(spec.pitch_bend, frames, timing)
    modulation = _control_values(spec.modulation, frames, timing)
    events = spec.note_events or _step_events(spec, quarter_notes_per_bar)
    wave_level = max(1.0, sum(wave.level for wave in sound.waves))

    for event_index, note in enumerate(events):
        start = timing.quarter_notes_to_frame(note.start)
        if start >= frames:
            continue
        note_frames = max(1, timing.quarter_notes_to_frame(note.duration))
        release = max(0, int(round(sound.release_ms * sample_rate / 1_000.0)))
        voice_frames = min(frames - start, note_frames + release)
        vibrato_rate = _automated(
            automation, "vibrato_rate_hz", sound.vibrato_rate_hz, start, voice_frames
        )
        vibrato_depth = _automated(
            automation, "vibrato_depth_cents", sound.vibrato_depth_cents, start, voice_frames
        )
        mod_depth = vibrato_depth + 50.0 * modulation[start : start + voice_frames]
        vibrato_phase = np.cumsum(vibrato_rate) / sample_rate
        vibrato = mod_depth * np.sin(2.0 * np.pi * vibrato_phase)
        expression_cents = 100.0 * bends[start : start + voice_frames] + vibrato
        voice = np.zeros(voice_frames, dtype=np.float64)
        base_frequency = note_frequency(note.pitch)
        for wave_index, wave in enumerate(sound.waves, start=1):
            level = _automated(
                automation, f"wave_{wave_index}_level", wave.level, start, voice_frames
            )
            detune = _automated(
                automation,
                f"wave_{wave_index}_detune_cents",
                wave.detune_cents,
                start,
                voice_frames,
            )
            tuning = 1_200 * wave.octave + 100 * wave.semitones + detune
            frequency = base_frequency * np.power(
                2.0, (tuning + expression_cents) / 1_200.0
            )
            phase = np.cumsum(frequency) / sample_rate
            phase -= phase[0]
            phase += wave.phase
            voice += level * _oscillator(wave, phase)
        voice /= wave_level
        noise_level = _automated(automation, "noise_level", sound.noise_level, start, voice_frames)
        if np.max(noise_level) > 0.0:
            generator = np.random.default_rng(sound.noise_seed + event_index)
            voice += noise_level * generator.uniform(-1.0, 1.0, voice_frames)
        envelope = _envelope(
            voice_frames,
            note_frames=note_frames,
            sample_rate=sample_rate,
            sound=sound,
            automation=automation,
            start=start,
        )
        note_gain = db_gain(spec.note_gains_db[event_index]) if spec.note_gains_db else 1.0
        output[start : start + voice_frames] += (
            0.38 * (note.velocity / 100.0) * note_gain * voice * envelope
        )

    cutoff = _automated(automation, "cutoff_hz", sound.cutoff_hz, 0, frames)
    resonance = _automated(automation, "resonance", sound.resonance, 0, frames)
    output = _filter(output, cutoff, resonance, sample_rate)
    drive = _automated(automation, "drive", sound.drive, 0, frames)
    drive_gain = 1.0 + drive * 10.0
    output = np.tanh(output * drive_gain) / np.tanh(drive_gain)
    if "gain_db" in automation and spec.automation_base_gain_db is not None:
        output *= db_envelope(automation["gain_db"] - spec.automation_base_gain_db)
    return np.asarray(output, dtype=np.float64)


def _automated(
    automation: Mapping[str, np.ndarray], name: str, default: float, start: int, frames: int
) -> np.ndarray:
    values = automation.get(name)
    if values is None:
        return np.full(frames, default, dtype=np.float64)
    return np.asarray(values[start : start + frames], dtype=np.float64)


def _step_events(spec: NativeSynthSpec, quarter_notes_per_bar: float) -> tuple[Note, ...]:
    clip_beats = spec.bars * quarter_notes_per_bar
    step = clip_beats / len(spec.sequence)
    gate = 0.8 if spec.gate is None else spec.gate
    return tuple(
        Note(pitch, index * step, step * gate, 100)
        for index, token in enumerate(spec.sequence)
        if token != "-"
        for pitch in token.split("+")
    )


def _control_values(
    points: tuple[ControlPoint, ...], frames: int, timing: MusicalTiming
) -> np.ndarray:
    return np.asarray(
        control_values(points, frames, timing=timing, default=0.0),
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
    automation: Mapping[str, np.ndarray],
    start: int,
) -> np.ndarray:
    positions = np.arange(frames, dtype=np.float64)
    attack = np.maximum(
        1.0, _automated(automation, "attack_ms", sound.attack_ms, start, frames)
        * sample_rate / 1_000.0
    )
    decay = np.maximum(
        1.0, _automated(automation, "decay_ms", sound.decay_ms, start, frames)
        * sample_rate / 1_000.0
    )
    sustain = _automated(automation, "sustain", sound.sustain, start, frames)
    release = np.maximum(
        1.0, _automated(automation, "release_ms", sound.release_ms, start, frames)
        * sample_rate / 1_000.0
    )
    envelope = sustain.copy()
    attack_mask = positions < attack
    envelope[attack_mask] = positions[attack_mask] / attack[attack_mask]
    decay_position = positions - attack
    decay_mask = ~attack_mask & (decay_position < decay)
    envelope[decay_mask] = 1.0 + (sustain[decay_mask] - 1.0) * (
        decay_position[decay_mask] / decay[decay_mask]
    )
    note_off = min(frames, note_frames)
    if note_off < frames:
        release_position = positions - note_off
        release_mask = release_position < release
        start_level = envelope[max(0, note_off - 1)]
        active_indices = np.arange(note_off, frames)[release_mask[note_off:]]
        envelope[active_indices] = start_level * (
            1.0 - release_position[active_indices] / release[active_indices]
        )
        envelope[np.arange(note_off, frames)[~release_mask[note_off:]]] = 0.0
    return envelope


def _filter(
    samples: np.ndarray, cutoff_hz: np.ndarray, resonance: np.ndarray, sample_rate: int
) -> np.ndarray:
    cutoff = np.clip(cutoff_hz, 20.0, sample_rate * 0.45)
    alpha = 1.0 - np.exp(-2.0 * np.pi * cutoff / sample_rate)
    first = 0.0
    second = 0.0
    output = np.empty_like(samples)
    for index, sample in enumerate(samples):
        first += alpha[index] * (sample - first)
        second += alpha[index] * (first - second)
        output[index] = second + resonance[index] * 2.0 * (first - second)
    return np.asarray(output, dtype=np.float64)


_DEFAULT = Uniwave()

definition = PluginDefinition(
    preset="uniwave",
    kind="instrument",
    parameters={
        "gain_db": Parameter(-6.0, -60.0, 12.0),
        "cutoff_hz": Parameter(_DEFAULT.cutoff_hz, 20.0, 20_000.0),
        "attack_ms": Parameter(_DEFAULT.attack_ms, 0.0, 5_000.0),
        "decay_ms": Parameter(_DEFAULT.decay_ms, 0.0, 5_000.0),
        "sustain": Parameter(_DEFAULT.sustain, 0.0, 1.0),
        "release_ms": Parameter(_DEFAULT.release_ms, 0.0, 5_000.0),
        "resonance": Parameter(_DEFAULT.resonance, 0.0, 0.95),
        "drive": Parameter(_DEFAULT.drive, 0.0, 1.0),
        "vibrato_rate_hz": Parameter(_DEFAULT.vibrato_rate_hz, 0.1, 20.0),
        "vibrato_depth_cents": Parameter(_DEFAULT.vibrato_depth_cents, 0.0, 100.0),
        "noise_level": Parameter(_DEFAULT.noise_level, 0.0, 1.0),
    },
    defaults=settings(_DEFAULT),
    midi_program=81,
    melodic=True,
    synth_processor=render,
)
