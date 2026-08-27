"""Small music-notation helpers shared by the public builders and renderer."""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass

from prism.errors import ProjectError

_NOTE = re.compile(r"^(?P<letter>[A-Ga-g])(?P<accidental>[#b]?)(?P<octave>-?\d{1,2})$")
_SEMITONES = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
_RESTS = {"-", ".", "r", "rest"}


@dataclass(frozen=True, slots=True)
class Note:
    """One MIDI note positioned in beats from the beginning of its clip."""

    pitch: str
    start: float
    duration: float
    velocity: int = 100

    def __post_init__(self) -> None:
        object.__setattr__(self, "pitch", normalize_note(self.pitch))
        if not math.isfinite(self.start) or self.start < 0.0:
            raise ProjectError("Note start must be finite and zero or greater.")
        if not math.isfinite(self.duration) or self.duration <= 0.0:
            raise ProjectError("Note duration must be finite and greater than zero.")
        if not isinstance(self.velocity, int) or not 1 <= self.velocity <= 127:
            raise ProjectError("Note velocity must be an integer between 1 and 127.")


@dataclass(frozen=True, slots=True)
class ControlPoint:
    """One pitch-bend or modulation value positioned in clip beats."""

    beat: float
    value: float


def rhythm_steps(pattern: str | Sequence[str]) -> tuple[str, ...]:
    """Normalize a readable ``x--- x---`` pattern into hit/rest steps."""

    raw = _raw_steps(pattern, expand_rhythm=True)
    result: list[str] = []
    for index, token in enumerate(raw, start=1):
        normalized = token.casefold()
        if normalized in {"x", "*"}:
            result.append("x")
        elif normalized in _RESTS:
            result.append("-")
        else:
            raise ProjectError(
                f"Rhythm step {index} is {token!r}; use 'x' for a hit and '-' for a rest."
            )
    if not any(step == "x" for step in result):
        raise ProjectError("A rhythm pattern needs at least one 'x' hit.")
    return tuple(result)


def note_steps(notes: str | Sequence[str]) -> tuple[str, ...]:
    """Normalize notes, rests, and ``+``-joined chords."""

    raw = _raw_steps(notes, expand_rhythm=False)
    result: list[str] = []
    for index, token in enumerate(raw, start=1):
        if token.casefold() in _RESTS:
            result.append("-")
            continue
        chord = token.split("+")
        if any(not note for note in chord):
            raise ProjectError(f"MIDI step {index} contains an incomplete chord: {token!r}.")
        try:
            result.append("+".join(normalize_note(note) for note in chord))
        except ValueError as error:
            raise ProjectError(f"MIDI step {index}: {error}") from error
    if not any(step != "-" for step in result):
        raise ProjectError("A MIDI sequence needs at least one note or chord.")
    return tuple(result)


def normalize_note(note: str) -> str:
    match = _NOTE.fullmatch(note.strip())
    if match is None:
        raise ValueError(f"invalid note {note!r}; use values such as C4, F#3, or Bb2")
    normalized = (
        f"{match.group('letter').upper()}{match.group('accidental')}"
        f"{int(match.group('octave'))}"
    )
    note_to_midi(normalized)
    return normalized


def note_to_midi(note: str) -> int:
    """Return the MIDI note number for scientific pitch notation."""

    match = _NOTE.fullmatch(note.strip())
    if match is None:
        raise ValueError(f"invalid note {note!r}; use values such as C4, F#3, or Bb2")
    accidental = match.group("accidental")
    semitone = _SEMITONES[match.group("letter").upper()]
    semitone += 1 if accidental == "#" else -1 if accidental == "b" else 0
    number = (int(match.group("octave")) + 1) * 12 + semitone
    if not 0 <= number <= 127:
        raise ValueError(f"note {note!r} is outside the MIDI range C-1 through G9")
    return number


def note_frequency(note: str) -> float:
    return 440.0 * math.pow(2.0, (note_to_midi(note) - 69) / 12.0)


def db_gain(value: float) -> float:
    return math.pow(10.0, value / 20.0)


def validate_gain(value: float, *, label: str) -> float:
    if not math.isfinite(value) or not -60.0 <= value <= 12.0:
        raise ProjectError(f"{label} must be between -60 and +12 dB.")
    return float(value)


def validate_pan(value: float) -> float:
    if not math.isfinite(value) or not -1.0 <= value <= 1.0:
        raise ProjectError("Track pan must be between -1.0 (left) and 1.0 (right).")
    return float(value)


def _raw_steps(value: str | Sequence[str], *, expand_rhythm: bool) -> tuple[str, ...]:
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise ProjectError("A pattern cannot be empty.")
        groups = text.replace("|", " ").replace(",", " ").split()
        can_expand = expand_rhythm and all(
            set(group.casefold()) <= {"x", "*", "-", "."} for group in groups
        )
        tokens = (
            tuple(character for group in groups for character in group)
            if can_expand
            else tuple(groups)
        )
    else:
        tokens = tuple(str(item).strip() for item in value)
    if not tokens or any(not token for token in tokens):
        raise ProjectError("A pattern cannot contain empty steps.")
    if len(tokens) > 512:
        raise ProjectError("A pattern cannot contain more than 512 steps.")
    return tokens
