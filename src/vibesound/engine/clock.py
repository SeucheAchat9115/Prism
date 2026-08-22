"""Exact sample-frame timing and musical quantization."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from vibesound.engine.errors import InvalidEngineCommandError
from vibesound.project.models import TransportState


def _ceil_fraction(value: Fraction) -> int:
    return -((-value.numerator) // value.denominator)


@dataclass(frozen=True, slots=True)
class TransportClock:
    """Convert the project's musical transport settings into frame positions."""

    sample_rate: int
    tempo_bpm: float
    time_signature_numerator: int
    time_signature_denominator: int
    quantization: str

    @classmethod
    def from_transport(cls, transport: TransportState) -> "TransportClock":
        return cls(
            sample_rate=transport.sample_rate,
            tempo_bpm=transport.tempo_bpm,
            time_signature_numerator=transport.time_signature_numerator,
            time_signature_denominator=transport.time_signature_denominator,
            quantization=transport.quantization,
        )

    @property
    def frames_per_quarter(self) -> Fraction:
        """Return exact frames per quarter note for the configured decimal tempo."""

        return Fraction(self.sample_rate * 60, 1) / Fraction(str(self.tempo_bpm))

    @property
    def frames_per_beat(self) -> Fraction:
        """Return exact frames per denominator-defined beat."""

        return self.frames_per_quarter * Fraction(4, self.time_signature_denominator)

    @property
    def frames_per_bar(self) -> Fraction:
        """Return exact frames per configured bar."""

        return self.frames_per_beat * self.time_signature_numerator

    def quantize(self, frame: int, quantization: str | None = None) -> int:
        """Return the current or next integer frame on the requested grid."""

        if not isinstance(frame, int) or isinstance(frame, bool) or frame < 0:
            raise InvalidEngineCommandError("frame must be a non-negative integer")
        grid = self.quantization if quantization is None else quantization
        if grid == "none":
            return frame
        if grid == "beat":
            grid_frames = self.frames_per_beat
        elif grid == "bar":
            grid_frames = self.frames_per_bar
        else:
            raise InvalidEngineCommandError(f"Unsupported quantization: {grid}")
        boundary_number = _ceil_fraction(Fraction(frame, 1) / grid_frames)
        return _ceil_fraction(boundary_number * grid_frames)
