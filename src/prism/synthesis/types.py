"""Internal deterministic synth contracts used by script-authored tracks."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from prism.music import note_steps, rhythm_steps

SynthPreset = Literal["kick", "snare", "hihat", "bass", "lead", "pad"]
SynthWaveform = Literal["sine", "triangle", "saw", "square"]

MAX_SYNTH_SECONDS = 120.0
PERCUSSION_PRESETS = frozenset({"kick", "snare", "hihat"})
MELODIC_PRESETS = frozenset({"bass", "lead", "pad"})

@dataclass(frozen=True, slots=True)
class NativeSynthSpec:
    preset: SynthPreset
    sequence: tuple[str, ...]
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
        if self.preset not in PERCUSSION_PRESETS | MELODIC_PRESETS:
            raise ValueError(f"Unknown built-in instrument: {self.preset!r}")
        if not 1 <= self.bars <= 256:
            raise ValueError("Synth clip bars must be between 1 and 256")
        normalized = (
            rhythm_steps(self.sequence)
            if self.preset in PERCUSSION_PRESETS
            else note_steps(self.sequence)
        )
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
