"""Internal deterministic synth contracts used by script-authored tracks."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, Mapping

from prism.errors import ProjectError
from prism.music import ControlPoint, Note, note_steps, rhythm_steps

if TYPE_CHECKING:
    import numpy as np

SynthPreset = str
SynthWaveform = Literal["sine", "triangle", "saw", "square"]

MAX_SYNTH_SECONDS = 120.0
PERCUSSION_PRESETS = frozenset({"kick", "snare", "hihat"})
MELODIC_PRESETS = frozenset({"bass", "lead", "pad"})


@dataclass(frozen=True, slots=True)
class SynthPatch:
    """Resolved defaults used by a stock melodic instrument."""

    waveform: SynthWaveform
    attack_ms: float
    decay_ms: float
    sustain_level: float
    release_ms: float
    cutoff_hz: float
    gate: float
    amplitude: float


@dataclass(frozen=True, slots=True)
class SynthWave:
    """One independently tuned oscillator inside a Uniwave instrument."""

    waveform: SynthWaveform = "saw"
    level: float = 1.0
    octave: int = 0
    semitones: int = 0
    detune_cents: float = 0.0
    phase: float = 0.0

    def __post_init__(self) -> None:
        if self.waveform not in {"sine", "triangle", "saw", "square"}:
            raise ProjectError("SynthWave waveform must be sine, triangle, saw, or square.")
        _uniwave_range(self.level, 0.0, 1.0, "SynthWave level")
        if not isinstance(self.octave, int) or not -3 <= self.octave <= 3:
            raise ProjectError("SynthWave octave must be an integer between -3 and 3.")
        if not isinstance(self.semitones, int) or not -12 <= self.semitones <= 12:
            raise ProjectError("SynthWave semitones must be an integer between -12 and 12.")
        _uniwave_range(self.detune_cents, -100.0, 100.0, "SynthWave detune_cents")
        _uniwave_range(self.phase, 0.0, 1.0, "SynthWave phase")


@dataclass(frozen=True, slots=True)
class Uniwave:
    """Prism's configurable multi-wave native synthesizer."""

    waves: tuple[SynthWave, ...] = field(default_factory=lambda: (SynthWave(),))
    attack_ms: float = 8.0
    decay_ms: float = 140.0
    sustain: float = 0.65
    release_ms: float = 180.0
    cutoff_hz: float = 5_000.0
    resonance: float = 0.15
    drive: float = 0.05
    vibrato_rate_hz: float = 5.0
    vibrato_depth_cents: float = 0.0
    noise_level: float = 0.0
    noise_seed: int = 0

    def __post_init__(self) -> None:
        waves = tuple(self.waves)
        object.__setattr__(self, "waves", waves)
        if not 1 <= len(waves) <= 4 or not all(isinstance(wave, SynthWave) for wave in waves):
            raise ProjectError("Uniwave needs between 1 and 4 SynthWave oscillators.")
        _uniwave_range(self.attack_ms, 0.0, 5_000.0, "Uniwave attack_ms")
        _uniwave_range(self.decay_ms, 0.0, 5_000.0, "Uniwave decay_ms")
        _uniwave_range(self.sustain, 0.0, 1.0, "Uniwave sustain")
        _uniwave_range(self.release_ms, 0.0, 5_000.0, "Uniwave release_ms")
        _uniwave_range(self.cutoff_hz, 20.0, 20_000.0, "Uniwave cutoff_hz")
        _uniwave_range(self.resonance, 0.0, 0.95, "Uniwave resonance")
        _uniwave_range(self.drive, 0.0, 1.0, "Uniwave drive")
        _uniwave_range(self.vibrato_rate_hz, 0.1, 20.0, "Uniwave vibrato_rate_hz")
        _uniwave_range(
            self.vibrato_depth_cents, 0.0, 100.0, "Uniwave vibrato_depth_cents"
        )
        _uniwave_range(self.noise_level, 0.0, 1.0, "Uniwave noise_level")
        if not isinstance(self.noise_seed, int) or not 0 <= self.noise_seed <= 4_294_967_295:
            raise ProjectError("Uniwave noise_seed must be between 0 and 4294967295.")

    @classmethod
    def bass(cls) -> Uniwave:
        """Return a solid two-wave bass starting point."""

        return cls(
            waves=(
                SynthWave("saw", level=0.8),
                SynthWave("square", level=0.3, octave=-1, detune_cents=4),
            ),
            attack_ms=4,
            decay_ms=110,
            sustain=0.58,
            release_ms=120,
            cutoff_hz=1_100,
            resonance=0.22,
            drive=0.18,
        )

    @classmethod
    def lead(cls) -> Uniwave:
        """Return a wide detuned lead starting point."""

        return cls(
            waves=(
                SynthWave("saw", level=0.7, detune_cents=-7),
                SynthWave("saw", level=0.7, detune_cents=7),
                SynthWave("square", level=0.2, octave=1),
            ),
            cutoff_hz=4_800,
            resonance=0.18,
            drive=0.12,
            vibrato_depth_cents=8,
        )

    @classmethod
    def pad(cls) -> Uniwave:
        """Return a soft layered pad starting point."""

        return cls(
            waves=(
                SynthWave("triangle", level=0.75, detune_cents=-5),
                SynthWave("triangle", level=0.75, detune_cents=5),
                SynthWave("sine", level=0.25, octave=1),
            ),
            attack_ms=220,
            decay_ms=420,
            sustain=0.78,
            release_ms=520,
            cutoff_hz=3_200,
            resonance=0.1,
            drive=0.03,
            vibrato_rate_hz=4.2,
            vibrato_depth_cents=5,
        )

@dataclass(frozen=True, slots=True)
class NativeSynthSpec:
    preset: SynthPreset
    sequence: tuple[str, ...]
    note_events: tuple[Note, ...] = ()
    note_gains_db: tuple[float, ...] = ()
    pitch_bend: tuple[ControlPoint, ...] = ()
    modulation: tuple[ControlPoint, ...] = ()
    uniwave: Uniwave | None = None
    automation: Mapping[str, "np.ndarray"] | None = None
    automation_base_gain_db: float | None = None
    frame_count: int | None = None
    bars: int = 1
    waveform: SynthWaveform | None = None
    attack_ms: float | None = None
    decay_ms: float | None = None
    sustain_level: float | None = None
    release_ms: float | None = None
    cutoff_hz: float | None = None
    gate: float | None = None
    gain_db: float = -3.0
    seed: int = 0

    def __post_init__(self) -> None:
        if not self.preset:
            raise ValueError("Instrument preset cannot be empty")
        if not 1 <= self.bars <= 256:
            raise ValueError("Synth clip bars must be between 1 and 256")
        if self.preset in PERCUSSION_PRESETS:
            normalized = rhythm_steps(self.sequence)
        elif self.note_events:
            normalized = self.sequence
        else:
            normalized = note_steps(self.sequence)
        object.__setattr__(self, "sequence", normalized)
        _range(self.gain_db, -60.0, 12.0, "Synth gain")
        if not 0 <= self.seed <= 4_294_967_295:
            raise ValueError("Synth seed must be between 0 and 4294967295")
        if self.preset in PERCUSSION_PRESETS:
            melodic = (
                self.waveform,
                self.attack_ms,
                self.decay_ms,
                self.sustain_level,
                self.release_ms,
                self.cutoff_hz,
                self.gate,
            )
            if any(value is not None for value in melodic):
                raise ValueError("Waveform, ADSR, cutoff, and gate apply to MIDI tracks only")
            return
        if self.note_gains_db and len(self.note_gains_db) != len(self.note_events):
            raise ValueError("note_gains_db must match note_events when supplied")
        if any(
            not math.isfinite(value) or not -60.0 <= value <= 12.0
            for value in self.note_gains_db
        ):
            raise ValueError("note_gains_db values must be between -60 and 12 dB")
        if self.waveform not in {None, "sine", "triangle", "saw", "square"}:
            raise ValueError("Waveform must be sine, triangle, saw, or square")
        _optional_range(self.attack_ms, 0.0, 5000.0, "Attack")
        _optional_range(self.decay_ms, 0.0, 5000.0, "Decay")
        _optional_range(self.sustain_level, 0.0, 1.0, "Sustain")
        _optional_range(self.release_ms, 0.0, 5000.0, "Release")
        _optional_range(self.cutoff_hz, 20.0, 20_000.0, "Cutoff")
        _optional_range(self.gate, 0.05, 1.0, "Gate")


def _optional_range(value: float | None, low: float, high: float, label: str) -> None:
    if value is not None:
        _range(value, low, high, label)


def _range(value: float, low: float, high: float, label: str) -> None:
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{label} must be between {low:g} and {high:g}")


def _uniwave_range(value: float, low: float, high: float, label: str) -> None:
    if not math.isfinite(value) or not low <= value <= high:
        raise ProjectError(f"{label} must be between {low:g} and {high:g}.")
