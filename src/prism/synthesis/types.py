"""Validated contracts for Prism's built-in deterministic synthesizer."""

from __future__ import annotations

import math
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SynthPreset = Literal["kick", "snare", "hihat", "bass", "lead", "pad"]
SynthWaveform = Literal["sine", "triangle", "saw", "square"]
SynthKind = Literal["percussion", "melodic"]

PERCUSSION_PRESETS = frozenset({"kick", "snare", "hihat"})
MELODIC_PRESETS = frozenset({"bass", "lead", "pad"})

_DEFAULT_SEQUENCES: dict[str, tuple[str, ...]] = {
    "kick": ("x", "-", "-", "-", "x", "-", "-", "-", "x", "-", "-", "-", "x", "-", "-", "-"),
    "snare": ("-", "-", "-", "-", "x", "-", "-", "-", "-", "-", "-", "-", "x", "-", "-", "-"),
    "hihat": ("x", "-", "x", "-", "x", "-", "x", "-", "x", "-", "x", "-", "x", "-", "x", "-"),
    "bass": ("C2", "-", "C2", "-", "G1", "-", "Bb1", "-"),
    "lead": ("C4", "E4", "G4", "Bb4", "G4", "E4", "D4", "-"),
    "pad": ("C3+E3+G3", "-", "F3+A3+C4", "-"),
}

_NOTE_PATTERN = re.compile(r"^(?P<letter>[A-Ga-g])(?P<accidental>[#b]?)(?P<octave>-?\d{1,2})$")
_SEMITONES = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


class SynthModel(BaseModel):
    """Strict base model shared by the public synthesis contracts."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class NativeSynthSpec(SynthModel):
    """One loop-aligned native synth request.

    A melodic token is a scientific-pitch note such as ``C4``, a chord such as
    ``C3+E3+G3``, or ``-`` for a rest. Percussion presets accept ``x`` and ``-``.
    """

    preset: SynthPreset
    sequence: list[str] = Field(default_factory=list, max_length=128)
    bars: int = Field(default=1, ge=1, le=32)
    waveform: SynthWaveform | None = None
    attack_ms: float | None = Field(default=None, ge=0.0, le=5000.0)
    decay_ms: float | None = Field(default=None, ge=0.0, le=5000.0)
    sustain_level: float | None = Field(default=None, ge=0.0, le=1.0)
    release_ms: float | None = Field(default=None, ge=0.0, le=5000.0)
    cutoff_hz: float | None = Field(default=None, ge=20.0, le=20_000.0)
    gate: float | None = Field(default=None, ge=0.05, le=1.0)
    gain_db: float = Field(default=-3.0, ge=-36.0, le=0.0)
    seed: int = Field(default=0, ge=0, le=4_294_967_295)

    @model_validator(mode="after")
    def normalize_and_validate_sequence(self) -> "NativeSynthSpec":
        sequence = self.sequence or list(_DEFAULT_SEQUENCES[self.preset])
        normalized: list[str] = []
        for index, raw_token in enumerate(sequence):
            token = raw_token.strip()
            if token.casefold() in {"-", ".", "r", "rest"}:
                normalized.append("-")
                continue
            if self.preset in PERCUSSION_PRESETS:
                if token.casefold() != "x":
                    raise ValueError(
                        f"percussion sequence token {index} must be 'x' or '-'"
                    )
                normalized.append("x")
                continue
            notes = token.split("+")
            if any(not note for note in notes):
                raise ValueError(f"melodic sequence token {index} is not a valid chord")
            for note in notes:
                note_frequency(note)
            normalized.append("+".join(_normalize_note(note) for note in notes))
        if not any(token != "-" for token in normalized):
            raise ValueError("sequence must contain at least one note or percussion hit")
        if self.preset in PERCUSSION_PRESETS:
            melodic_fields = (
                "waveform",
                "attack_ms",
                "decay_ms",
                "sustain_level",
                "release_ms",
                "cutoff_hz",
                "gate",
            )
            if any(getattr(self, field) is not None for field in melodic_fields):
                raise ValueError("waveform, ADSR, cutoff, and gate apply only to melodic presets")
        self.sequence = normalized
        return self


class NativeSynthPresetInfo(SynthModel):
    """Discoverable metadata for one built-in preset."""

    name: SynthPreset
    kind: SynthKind
    description: str
    default_sequence: list[str]
    default_waveform: SynthWaveform | None = None


def note_frequency(note: str) -> float:
    """Convert one scientific-pitch token to an equal-tempered frequency."""

    match = _NOTE_PATTERN.fullmatch(note.strip())
    if match is None:
        raise ValueError(f"invalid note {note!r}; use values such as C4, F#3, or Bb2")
    letter = match.group("letter").upper()
    accidental = match.group("accidental")
    octave = int(match.group("octave"))
    semitone = _SEMITONES[letter] + (1 if accidental == "#" else -1 if accidental == "b" else 0)
    midi_note = (octave + 1) * 12 + semitone
    if not 0 <= midi_note <= 127:
        raise ValueError(f"note {note!r} is outside the MIDI pitch range C-1 through G9")
    return 440.0 * math.pow(2.0, (midi_note - 69) / 12.0)


def default_sequence(preset: SynthPreset) -> list[str]:
    """Return a mutable copy of one preset's tutorial-friendly sequence."""

    return list(_DEFAULT_SEQUENCES[preset])


def _normalize_note(note: str) -> str:
    match = _NOTE_PATTERN.fullmatch(note.strip())
    assert match is not None
    return f"{match.group('letter').upper()}{match.group('accidental')}{int(match.group('octave'))}"
