from __future__ import annotations

import pytest

from prism import ProjectError
from prism.music import note_frequency, note_steps, note_to_midi, rhythm_steps


def test_readable_rhythm_notation_accepts_grouping() -> None:
    assert rhythm_steps("x--- x-x- | x--- x---") == tuple("x---x-x-x---x---")
    assert rhythm_steps("x, -, *, .") == ("x", "-", "x", "-")


def test_note_notation_supports_rests_accidentals_and_chords() -> None:
    assert note_steps("C4 - F#4+A4 Bb3") == ("C4", "-", "F#4+A4", "Bb3")
    assert note_to_midi("C4") == 60
    assert note_to_midi("Bb3") == 58
    assert note_frequency("A4") == pytest.approx(440.0)


@pytest.mark.parametrize("value", ("", "----", "x--q"))
def test_invalid_rhythm_is_explained(value: str) -> None:
    with pytest.raises(ProjectError):
        rhythm_steps(value)


def test_invalid_midi_note_is_explained() -> None:
    with pytest.raises(ProjectError, match="MIDI step 2"):
        note_steps("C4 H4")
