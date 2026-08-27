"""Deterministic native synthesis used for playable Prism audio assets."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from prism.music import note_frequency
from prism.synthesis.types import (
    NativeSynthSpec,
    SynthWaveform,
)

_MAX_SYNTH_SECONDS = 120.0


@dataclass(frozen=True, slots=True)
class _Patch:
    waveform: SynthWaveform
    attack_ms: float
    decay_ms: float
    sustain_level: float
    release_ms: float
    cutoff_hz: float
    gate: float
    amplitude: float


_PATCHES: dict[str, _Patch] = {
    "bass": _Patch("saw", 5.0, 100.0, 0.58, 110.0, 900.0, 0.78, 0.46),
    "lead": _Patch("square", 8.0, 90.0, 0.62, 140.0, 3_600.0, 0.82, 0.30),
    "pad": _Patch("triangle", 180.0, 380.0, 0.76, 420.0, 2_400.0, 0.92, 0.26),
}


def render_native_synth(
    spec: NativeSynthSpec,
    *,
    sample_rate: int,
    tempo_bpm: float,
    beats_per_bar: int = 4,
) -> np.ndarray:
    """Render one loop-aligned spec to deterministic mono samples."""

    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")
    if not math.isfinite(tempo_bpm) or tempo_bpm <= 0:
        raise ValueError("tempo_bpm must be positive and finite")
    if beats_per_bar <= 0:
        raise ValueError("beats_per_bar must be positive")
    seconds = spec.bars * beats_per_bar * 60.0 / tempo_bpm
    if seconds > _MAX_SYNTH_SECONDS:
        raise ValueError(f"native synth output cannot exceed {_MAX_SYNTH_SECONDS:g} seconds")
    frames = max(1, int(round(seconds * sample_rate)))
    boundaries = np.rint(np.linspace(0, frames, len(spec.sequence) + 1)).astype(np.int64)
    samples = np.zeros(frames, dtype=np.float64)
    if spec.preset in {"kick", "snare", "hihat"}:
        _render_percussion(samples, boundaries, spec, sample_rate)
    else:
        _render_melodic(samples, boundaries, spec, sample_rate)
    gain = 10.0 ** (spec.gain_db / 20.0)
    samples *= gain
    samples = np.tanh(samples * 1.15) / math.tanh(1.15)
    return np.asarray(np.clip(samples, -1.0, 1.0), dtype=np.float64)


def _render_percussion(
    output: np.ndarray,
    boundaries: np.ndarray,
    spec: NativeSynthSpec,
    sample_rate: int,
) -> None:
    rng = np.random.default_rng(spec.seed)
    for index, token in enumerate(spec.sequence):
        if token == "-":
            continue
        start = int(boundaries[index])
        step_frames = max(1, int(boundaries[index + 1]) - start)
        if spec.preset == "kick":
            length = min(output.size - start, step_frames, max(1, int(0.42 * sample_rate)))
            time = np.arange(length, dtype=np.float64) / sample_rate
            frequency = 48.0 + 115.0 * np.exp(-24.0 * time)
            phase = 2.0 * np.pi * np.cumsum(frequency) / sample_rate
            envelope = np.exp(-10.5 * time)
            hit = 0.94 * envelope * np.sin(phase)
            hit[: min(length, max(1, sample_rate // 1000))] += 0.12
        elif spec.preset == "snare":
            length = min(output.size - start, step_frames, max(1, int(0.24 * sample_rate)))
            time = np.arange(length, dtype=np.float64) / sample_rate
            noise = rng.standard_normal(length)
            high = np.concatenate((noise[:1], np.diff(noise)))
            envelope = np.exp(-17.0 * time)
            hit = envelope * (
                0.34 * high + 0.22 * np.sin(2.0 * np.pi * 185.0 * time)
            )
        else:
            length = min(output.size - start, step_frames, max(1, int(0.085 * sample_rate)))
            time = np.arange(length, dtype=np.float64) / sample_rate
            noise = rng.standard_normal(length)
            high = np.concatenate((noise[:1], np.diff(noise)))
            hit = 0.24 * high * np.exp(-58.0 * time)
        output[start : start + length] += hit


def _render_melodic(
    output: np.ndarray,
    boundaries: np.ndarray,
    spec: NativeSynthSpec,
    sample_rate: int,
) -> None:
    default = _PATCHES[spec.preset]
    patch = _Patch(
        waveform=spec.waveform or default.waveform,
        attack_ms=default.attack_ms if spec.attack_ms is None else spec.attack_ms,
        decay_ms=default.decay_ms if spec.decay_ms is None else spec.decay_ms,
        sustain_level=(
            default.sustain_level if spec.sustain_level is None else spec.sustain_level
        ),
        release_ms=default.release_ms if spec.release_ms is None else spec.release_ms,
        cutoff_hz=default.cutoff_hz if spec.cutoff_hz is None else spec.cutoff_hz,
        gate=default.gate if spec.gate is None else spec.gate,
        amplitude=default.amplitude,
    )
    for index, token in enumerate(spec.sequence):
        if token == "-":
            continue
        start = int(boundaries[index])
        step_frames = max(1, int(boundaries[index + 1]) - start)
        note_off = max(1, int(round(step_frames * patch.gate)))
        release_frames = max(0, int(round(patch.release_ms * sample_rate / 1000.0)))
        voice_frames = min(output.size - start, note_off + release_frames)
        chord = token.split("+")
        chord_output = np.zeros(voice_frames, dtype=np.float64)
        for note in chord:
            frequency = note_frequency(note)
            time = np.arange(voice_frames, dtype=np.float64) / sample_rate
            chord_output += _oscillator(patch.waveform, frequency, time)
        chord_output /= math.sqrt(len(chord))
        envelope = _adsr_envelope(
            voice_frames,
            note_off=note_off,
            sample_rate=sample_rate,
            attack_ms=patch.attack_ms,
            decay_ms=patch.decay_ms,
            sustain_level=patch.sustain_level,
            release_ms=patch.release_ms,
        )
        output[start : start + voice_frames] += patch.amplitude * chord_output * envelope
    window = int(round(sample_rate / max(40.0, patch.cutoff_hz * 2.0)))
    window = max(1, min(64, output.size, window))
    if window > 1:
        kernel = np.full(window, 1.0 / window, dtype=np.float64)
        output[:] = np.convolve(output, kernel, mode="same")


def _oscillator(waveform: str, frequency: float, time: np.ndarray) -> np.ndarray:
    phase_cycles = frequency * time
    if waveform == "sine":
        return np.sin(2.0 * np.pi * phase_cycles)
    if waveform == "triangle":
        return 2.0 * np.abs(2.0 * (phase_cycles - np.floor(phase_cycles + 0.5))) - 1.0
    if waveform == "saw":
        return 2.0 * (phase_cycles - np.floor(phase_cycles + 0.5))
    return np.where(np.sin(2.0 * np.pi * phase_cycles) >= 0.0, 1.0, -1.0)


def _adsr_envelope(
    frames: int,
    *,
    note_off: int,
    sample_rate: int,
    attack_ms: float,
    decay_ms: float,
    sustain_level: float,
    release_ms: float,
) -> np.ndarray:
    attack = max(0, int(round(attack_ms * sample_rate / 1000.0)))
    decay = max(0, int(round(decay_ms * sample_rate / 1000.0)))
    release = max(0, int(round(release_ms * sample_rate / 1000.0)))
    envelope = np.full(frames, sustain_level, dtype=np.float64)
    if attack > 0:
        attack_end = min(frames, attack)
        envelope[:attack_end] = np.linspace(0.0, 1.0, attack_end, endpoint=False)
    else:
        attack_end = 0
    if decay > 0 and attack_end < frames:
        decay_end = min(frames, attack_end + decay)
        envelope[attack_end:decay_end] = np.linspace(
            1.0,
            sustain_level,
            decay_end - attack_end,
            endpoint=False,
        )
    note_off = min(frames, note_off)
    if note_off < frames:
        start_level = envelope[max(0, note_off - 1)]
        if release > 0:
            release_end = min(frames, note_off + release)
            envelope[note_off:release_end] = np.linspace(
                start_level,
                0.0,
                release_end - note_off,
                endpoint=False,
            )
            envelope[release_end:] = 0.0
        else:
            envelope[note_off:] = 0.0
    return envelope
