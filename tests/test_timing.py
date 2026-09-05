from __future__ import annotations

import math
from pathlib import Path

import pytest

from prism import Project, ProjectError
from prism.effects import parameter_values
from prism.music import Note
from prism.timing import (
    CANONICAL_TIMING_VERSION,
    LEGACY_TIMING_VERSION,
    MusicalTiming,
    TimeSignature,
)


def _midi_tracks(payload: bytes) -> list[bytes]:
    tracks: list[bytes] = []
    position = 14
    while position < len(payload):
        assert payload[position : position + 4] == b"MTrk"
        length = int.from_bytes(payload[position + 4 : position + 8], "big")
        start = position + 8
        tracks.append(payload[start : start + length])
        position = start + length
    return tracks


def _midi_events(track: bytes) -> list[tuple[int, int, bytes]]:
    events: list[tuple[int, int, bytes]] = []
    position = 0
    tick = 0
    running_status: int | None = None
    while position < len(track):
        delta, position = _read_variable_length(track, position)
        tick += delta
        status = track[position]
        if status < 0x80:
            if running_status is None:
                raise AssertionError("MIDI running status was used without a status byte")
            status = running_status
        else:
            position += 1
            running_status = status if status < 0xF0 else None
        if status == 0xFF:
            kind = track[position]
            position += 1
            length, position = _read_variable_length(track, position)
            body = track[position : position + length]
            position += length
            events.append((tick, kind, body))
            if kind == 0x2F:
                break
        elif status in {0xF0, 0xF7}:
            length, position = _read_variable_length(track, position)
            position += length
        else:
            data_length = 1 if status & 0xE0 == 0xC0 else 2
            if track[position] >= 0x80:
                position += data_length
            else:
                position += data_length - 1
    return events


def _read_variable_length(payload: bytes, position: int) -> tuple[int, int]:
    value = 0
    while True:
        byte = payload[position]
        position += 1
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            return value, position


@pytest.mark.parametrize(
    ("numerator", "denominator", "quarter_notes"),
    ((4, 4, 4.0), (3, 4, 3.0), (6, 8, 3.0), (7, 8, 3.5)),
)
def test_meter_defines_audio_duration_and_midi_end_tick(
    project_script: Path,
    numerator: int,
    denominator: int,
    quarter_notes: float,
) -> None:
    song = Project(
        f"{numerator}-{denominator}",
        prism_version="test",
        tempo=120,
        sample_rate=8_000,
        beats_per_bar=numerator,
        beat_unit=denominator,  # type: ignore[arg-type]
        _script=project_script,
    )
    song.track("Kick").drum("kick", "x")
    song.section("One", bars=1)

    expected_frames = round(quarter_notes * 60.0 / 120.0 * 8_000)
    assert song.timing.quarter_notes_per_bar == quarter_notes
    assert song.frames_per_bar == expected_frames
    assert song.validate().duration_seconds == pytest.approx(
        quarter_notes * 60.0 / 120.0
    )

    rendered = song.render("renders/meter.wav")
    assert rendered.frames == expected_frames
    payload = song.export_midi("renders/meter.mid").path.read_bytes()
    conductor = _midi_events(_midi_tracks(payload)[0])
    assert (0, 0x58, bytes((numerator, int(math.log2(denominator)), 24, 8))) in conductor
    assert (round(quarter_notes * 480), 0x2F, b"") in conductor


@pytest.mark.parametrize(
    ("meter", "quarter_notes"),
    (((4, 4), 4.0), ((3, 4), 3.0), ((6, 8), 3.0), ((7, 8), 3.5)),
)
def test_note_positions_use_quarter_notes_in_every_meter(
    project_script: Path, meter: tuple[int, int], quarter_notes: float
) -> None:
    numerator, denominator = meter
    song = Project(
        f"Notes {numerator}-{denominator}",
        prism_version="test",
        tempo=120,
        sample_rate=8_000,
        beats_per_bar=numerator,
        beat_unit=denominator,  # type: ignore[arg-type]
        _script=project_script,
    )
    start = quarter_notes - 0.5
    track = song.track("Lead").midi(
        [Note("C4", start=start, duration=0.25)], instrument="lead", bars=1
    )
    song.section("One", bars=1)

    clip = track.clips[0].clip
    assert clip.events[0].start == start  # type: ignore[union-attr]
    assert song.timing.quarter_notes_to_frame(start) == round(start * 60 / 120 * 8_000)
    assert song.timing.bars_to_frame(1) == round(quarter_notes * 60 / 120 * 8_000)


@pytest.mark.parametrize("meter", ((4, 4), (3, 4), (6, 8), (7, 8)))
def test_automation_shares_the_meter_conversion(
    project_script: Path, meter: tuple[int, int]
) -> None:
    numerator, denominator = meter
    song = Project(
        f"Automation {numerator}-{denominator}",
        prism_version="test",
        tempo=120,
        sample_rate=8_000,
        beats_per_bar=numerator,
        beat_unit=denominator,  # type: ignore[arg-type]
        _script=project_script,
    )
    track = song.track("Lead").midi("C4", instrument="lead")
    gain = track.effect("gain", gain_db=-60)
    song.section("Two Bars", bars=2)
    song.automation(
        "Fade",
        target=gain,
        parameter="gain_db",
        points=[(0, -60), (2, 0)],
    )

    end = song.timing.bar_to_frame(2)
    values = parameter_values(song, gain, "gain_db", end)
    assert values[song.timing.bar_to_frame(1)] == pytest.approx(-30.0, abs=0.01)


def test_automation_uses_absolute_frame_boundaries_without_bar_drift(
    project_script: Path,
) -> None:
    song = Project(
        "Automation Timing",
        prism_version="test",
        tempo=123.45,
        sample_rate=8_000,
        beats_per_bar=7,
        beat_unit=8,
        _script=project_script,
    )
    track = song.track("Lead").midi("C4", instrument="lead")
    gain = track.effect("gain", gain_db=-60)
    song.section("Long", bars=100)
    song.automation(
        "Fade",
        target=gain,
        parameter="gain_db",
        points=[(0, -60), (100, 0)],
    )

    values = parameter_values(song, gain, "gain_db", song.timing.bar_to_frame(100))
    boundary = song.timing.bar_to_frame(50)
    assert values[boundary] == pytest.approx(-30.0, abs=0.01)
    assert song.timing.bar_to_frame(10_000) == round(
        song.timing.bars_to_seconds(10_000) * song.sample_rate
    )
    assert song.timing.bar_to_frame(10_000) != song.frames_per_bar * 10_000


def test_explicit_legacy_compatibility_does_not_depend_on_prism_version(
    project_script: Path,
) -> None:
    canonical = Project(
        "Canonical",
        prism_version="legacy-looking-project",
        beats_per_bar=6,
        beat_unit=8,
        _script=project_script,
    )
    legacy = Project(
        "Legacy",
        prism_version="anything",
        beats_per_bar=6,
        beat_unit=8,
        timing_compatibility=LEGACY_TIMING_VERSION,
        _script=project_script,
    )

    assert canonical.timing.compatibility == CANONICAL_TIMING_VERSION
    assert canonical.timing.quarter_notes_per_bar == 3.0
    assert legacy.timing.quarter_notes_per_bar == 6.0
    assert legacy.frames_per_bar == 2 * canonical.frames_per_bar
    assert canonical.configuration()["timing_compatibility"] == CANONICAL_TIMING_VERSION
    assert legacy.configuration()["timing_compatibility"] == LEGACY_TIMING_VERSION


@pytest.mark.parametrize(
    ("kwargs", "message"),
    (
        ({"beats_per_bar": 0}, "numerator"),
        ({"beats_per_bar": 3.5}, "numerator"),
        ({"beat_unit": 3}, "denominator"),
        ({"tempo": 0}, "Tempo"),
        ({"tempo": float("nan")}, "Tempo"),
        ({"timing_compatibility": "v2"}, "Timing compatibility"),
    ),
)
def test_invalid_timing_input_has_a_specific_error(
    project_script: Path, kwargs: dict[str, object], message: str
) -> None:
    with pytest.raises(ProjectError, match=message):
        Project("Invalid timing", prism_version="test", _script=project_script, **kwargs)  # type: ignore[arg-type]


def test_timing_conversion_rejects_invalid_ranges() -> None:
    timing = MusicalTiming(time_signature=TimeSignature(4, 4))
    with pytest.raises(ValueError, match="finite"):
        timing.bar_to_frame(float("nan"))
    with pytest.raises(ValueError, match="End bar"):
        timing.bar_range_to_frames(2, 1)
    with pytest.raises(ValueError, match="ticks_per_beat"):
        timing.quarter_notes_to_ticks(1, 0)
