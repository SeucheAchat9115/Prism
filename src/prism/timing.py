"""Canonical musical-to-audio timing conversions.

Prism's internal musical coordinate is a quarter-note beat.  A time signature
only describes how many of those beats make one bar; it does not change what a
``Note.start`` or ``Note.duration`` means.  This module is the single boundary
between those musical coordinates, wall-clock seconds, audio sample frames,
and explicitly quantized MIDI ticks.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Literal, Protocol, cast

from prism.errors import ProjectError

TimingCompatibility = Literal["quarter_note_v1", "legacy_numerator_v0"]

CANONICAL_TIMING_VERSION: TimingCompatibility = "quarter_note_v1"
LEGACY_TIMING_VERSION: TimingCompatibility = "legacy_numerator_v0"
_SUPPORTED_DENOMINATORS = (1, 2, 4, 8, 16)


@dataclass(frozen=True, slots=True)
class TimeSignature:
    """A validated producer-facing meter.

    ``numerator`` counts denominator-notes in the written meter.  The
    canonical quarter-note length of a bar is therefore ``numerator * 4 /
    denominator``.  For example, 6/8 is three quarter-note beats per bar.
    """

    numerator: int = 4
    denominator: int = 4

    def __post_init__(self) -> None:
        if (
            isinstance(self.numerator, bool)
            or not isinstance(self.numerator, int)
            or not 1 <= self.numerator <= 32
        ):
            raise ProjectError(
                "Time signature numerator must be an integer between 1 and 32."
            )
        if (
            isinstance(self.denominator, bool)
            or not isinstance(self.denominator, int)
            or self.denominator not in _SUPPORTED_DENOMINATORS
        ):
            choices = ", ".join(str(value) for value in _SUPPORTED_DENOMINATORS)
            raise ProjectError(f"Time signature denominator must be one of {choices}.")

    @property
    def quarter_notes_per_bar(self) -> float:
        """Return this meter's canonical bar length as quarter notes."""

        return float(Fraction(self.numerator * 4, self.denominator))

    @property
    def denominator_power(self) -> int:
        """Return the base-two denominator exponent used by MIDI metadata."""

        return self.denominator.bit_length() - 1

    def as_tuple(self) -> tuple[int, int]:
        """Return the written ``(numerator, denominator)`` pair."""

        return self.numerator, self.denominator


class TimingMap(Protocol):
    """Interface consumed by scheduling code and replaceable by tempo maps.

    Future tempo-map implementations can keep the same quarter-note and bar
    coordinates while replacing only the conversion at this boundary.
    """

    @property
    def quarter_notes_per_bar(self) -> float: ...

    def bar_to_frame(self, absolute_bar: float) -> int: ...

    def quarter_notes_to_frame(self, quarter_notes: float) -> int: ...

    def quarter_notes_to_ticks(self, quarter_notes: float, ticks_per_beat: int) -> int: ...


@dataclass(frozen=True, slots=True)
class MusicalTiming:
    """Constant-tempo timing used by the current offline renderer.

    The default ``quarter_note_v1`` mode uses ``N * 4 / D`` quarter notes per
    bar.  ``legacy_numerator_v0`` is an explicit migration escape hatch for
    projects authored against Prism's old behavior, where the numerator was
    incorrectly treated as a number of quarter notes.  The mode is never
    inferred from a project version string.
    """

    tempo_bpm: float = 120.0
    sample_rate: int = 44_100
    time_signature: TimeSignature | tuple[int, int] = field(default_factory=TimeSignature)
    compatibility: TimingCompatibility = CANONICAL_TIMING_VERSION

    def __post_init__(self) -> None:
        try:
            tempo = float(self.tempo_bpm)
        except (TypeError, ValueError) as error:
            raise ProjectError("Tempo must be between 20 and 300 BPM.") from error
        if not math.isfinite(tempo) or not 20.0 <= tempo <= 300.0:
            raise ProjectError("Tempo must be between 20 and 300 BPM.")
        if (
            isinstance(self.sample_rate, bool)
            or not isinstance(self.sample_rate, int)
            or not 8_000 <= self.sample_rate <= 192_000
        ):
            raise ProjectError("Sample rate must be between 8000 and 192000 Hz.")
        if self.compatibility not in (
            CANONICAL_TIMING_VERSION,
            LEGACY_TIMING_VERSION,
        ):
            raise ProjectError(
                "Timing compatibility must be 'quarter_note_v1' or "
                "'legacy_numerator_v0'."
            )
        signature = self.time_signature
        if isinstance(signature, tuple):
            try:
                signature = TimeSignature(*signature)
            except TypeError as error:
                raise ProjectError(
                    "Time signature must be a (numerator, denominator) pair."
                ) from error
        if not isinstance(signature, TimeSignature):
            raise ProjectError("Time signature must be a (numerator, denominator) pair.")
        object.__setattr__(self, "tempo_bpm", tempo)
        object.__setattr__(self, "time_signature", signature)

    @property
    def numerator(self) -> int:
        """Return the written meter numerator."""

        return self._signature().numerator

    @property
    def denominator(self) -> int:
        """Return the written meter denominator."""

        return self._signature().denominator

    @property
    def denominator_power(self) -> int:
        """Return the MIDI time-signature denominator exponent."""

        return self._signature().denominator_power

    @property
    def quarter_notes_per_bar(self) -> float:
        """Return the configured bar length in canonical quarter-note beats."""

        if self.compatibility == LEGACY_TIMING_VERSION:
            return float(self.numerator)
        return self._signature().quarter_notes_per_bar

    @property
    def seconds_per_quarter_note(self) -> float:
        """Return the duration of one canonical quarter-note beat."""

        return 60.0 / self.tempo_bpm

    @property
    def seconds_per_bar(self) -> float:
        """Return the duration of one configured bar."""

        return self.quarter_notes_per_bar * self.seconds_per_quarter_note

    @property
    def frames_per_quarter_note(self) -> float:
        """Return the unrounded number of audio frames in one quarter note."""

        return self.sample_rate * self.seconds_per_quarter_note

    @property
    def microseconds_per_quarter_note(self) -> int:
        """Return MIDI's integer microseconds-per-quarter-note value."""

        return int(round(self.seconds_per_quarter_note * 1_000_000.0))

    def bars_to_quarter_notes(self, bars: float) -> float:
        """Convert a non-negative bar position or length to quarter notes."""

        return float(self._bars_fraction(bars) * self._quarter_notes_per_bar_fraction())

    def bars_to_seconds(self, bars: float) -> float:
        """Convert a bar position or length to seconds without frame rounding."""

        return self.bars_to_quarter_notes(bars) * self.seconds_per_quarter_note

    def quarter_notes_to_seconds(self, quarter_notes: float) -> float:
        """Convert a non-negative quarter-note position or length to seconds."""

        return self._non_negative_float(quarter_notes, "Quarter-note position") * (
            self.seconds_per_quarter_note
        )

    def seconds_to_frames(self, seconds: float) -> int:
        """Round a non-negative absolute duration to the nearest sample frame."""

        value = self._non_negative_float(seconds, "Seconds")
        return int(round(value * self.sample_rate))

    def quarter_notes_to_frame(self, quarter_notes: float) -> int:
        """Convert an absolute quarter-note position to an integer frame."""

        return self.seconds_to_frames(self.quarter_notes_to_seconds(quarter_notes))

    def quarter_notes_to_frames(self, quarter_notes: float) -> int:
        """Plural alias for :meth:`quarter_notes_to_frame`."""

        return self.quarter_notes_to_frame(quarter_notes)

    def bars_to_frames(self, bars: float) -> int:
        """Convert an absolute bar position to an integer frame boundary.

        Callers should pass absolute positions here and subtract two returned
        boundaries for a range.  This prevents per-bar rounding from
        accumulating over long arrangements.
        """

        return self.quarter_notes_to_frame(self.bars_to_quarter_notes(bars))

    def bar_to_frame(self, absolute_bar: float) -> int:
        """Convert an absolute bar position to an integer frame boundary."""

        return self.bars_to_frames(absolute_bar)

    def bars_to_frame(self, absolute_bar: float) -> int:
        """Singular alias for :meth:`bars_to_frames`."""

        return self.bars_to_frames(absolute_bar)

    def bar_range_to_frames(self, start_bar: float, end_bar: float) -> int:
        """Return the frame length between two absolute bar positions."""

        start = self._bars_fraction(start_bar)
        end = self._bars_fraction(end_bar)
        if end < start:
            raise ValueError("End bar must not be before start bar.")
        return self.bars_to_frames(float(end)) - self.bars_to_frames(float(start))

    def quarter_notes_to_ticks(self, quarter_notes: float, ticks_per_beat: int) -> int:
        """Quantize an absolute quarter-note position to MIDI ticks.

        MIDI ticks are deliberately independent from audio sample-frame
        scheduling.  Every caller supplies its MIDI resolution explicitly.
        """

        if (
            isinstance(ticks_per_beat, bool)
            or not isinstance(ticks_per_beat, int)
            or ticks_per_beat <= 0
        ):
            raise ValueError("ticks_per_beat must be a positive integer.")
        value = self._non_negative_float(quarter_notes, "Quarter-note position")
        return int(round(value * ticks_per_beat))

    def bars_to_ticks(self, bars: float, ticks_per_beat: int) -> int:
        """Quantize an absolute bar position to MIDI ticks."""

        return self.quarter_notes_to_ticks(
            self.bars_to_quarter_notes(bars), ticks_per_beat
        )

    @staticmethod
    def _non_negative_float(value: float, label: str) -> float:
        try:
            resolved = float(value)
        except (TypeError, ValueError) as error:
            raise ValueError(f"{label} must be finite and zero or greater.") from error
        if not math.isfinite(resolved) or resolved < 0.0:
            raise ValueError(f"{label} must be finite and zero or greater.")
        return resolved

    def _bars_fraction(self, value: float) -> Fraction:
        resolved = self._non_negative_float(value, "Bar position")
        return Fraction(str(resolved))

    def _quarter_notes_per_bar_fraction(self) -> Fraction:
        if self.compatibility == LEGACY_TIMING_VERSION:
            return Fraction(self.numerator, 1)
        signature = self._signature()
        return Fraction(signature.numerator * 4, signature.denominator)

    def _signature(self) -> TimeSignature:
        """Return the normalized signature established during initialization."""

        return cast(TimeSignature, self.time_signature)


__all__ = [
    "CANONICAL_TIMING_VERSION",
    "LEGACY_TIMING_VERSION",
    "MusicalTiming",
    "TimeSignature",
    "TimingCompatibility",
    "TimingMap",
]
