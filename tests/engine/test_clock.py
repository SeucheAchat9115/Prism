from fractions import Fraction

import pytest

from prism.engine import TransportClock
from prism.engine.errors import InvalidEngineCommandError
from prism.project.models import TransportState


def test_clock_uses_exact_musical_frame_lengths() -> None:
    clock = TransportClock.from_transport(
        TransportState(sample_rate=44100, tempo_bpm=120, quantization="bar")
    )

    assert clock.frames_per_quarter == Fraction(22050)
    assert clock.frames_per_beat == Fraction(22050)
    assert clock.frames_per_bar == Fraction(88200)
    assert clock.quantize(0) == 0
    assert clock.quantize(88200) == 88200
    assert clock.quantize(88201) == 176400


def test_clock_respects_time_signature_denominator() -> None:
    clock = TransportClock.from_transport(
        TransportState(
            sample_rate=8,
            tempo_bpm=120,
            time_signature_numerator=6,
            time_signature_denominator=8,
            quantization="bar",
        )
    )

    assert clock.frames_per_beat == Fraction(2)
    assert clock.frames_per_bar == Fraction(12)
    assert clock.quantize(13) == 24


def test_clock_rounds_fractional_boundaries_up() -> None:
    clock = TransportClock.from_transport(
        TransportState(sample_rate=44100, tempo_bpm=123.0, quantization="beat")
    )

    assert clock.frames_per_beat == Fraction(882000, 41)
    assert clock.quantize(21512) == 21513


def test_clock_rejects_invalid_frames_and_quantization() -> None:
    clock = TransportClock.from_transport(TransportState(quantization="none"))

    with pytest.raises(InvalidEngineCommandError):
        clock.quantize(-1)
    with pytest.raises(InvalidEngineCommandError):
        clock.quantize(0, "invalid")
