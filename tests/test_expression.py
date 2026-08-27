from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from prism import Note, Project, ProjectError


def _events(song: Project) -> object:
    configuration = song.configuration()
    return configuration["tracks"][0]["clips"][0]["events"]  # type: ignore[index]


def test_positioned_notes_control_timing_duration_and_velocity(
    project_script: Path,
) -> None:
    song = Project(
        "Expressive Notes",
        prism_version="test",
        tempo=120,
        sample_rate=8_000,
        normalize=False,
        _script=project_script,
    )
    lead = song.track("Lead").midi(
        [
            Note("c4", start=0.5, duration=0.25, velocity=45),
            Note("C4", start=1.5, duration=0.5, velocity=120),
        ],
        bars=1,
    )
    song.section("Only", bars=1, tracks=[lead])

    result = song.render("renders/expression.wav")
    midi = song.export_midi("renders/expression.mid").path.read_bytes()
    samples, _ = sf.read(result.path, dtype="float64", always_2d=True)
    beat = int(8_000 * 60 / 120)

    assert np.max(np.abs(samples[: beat // 2])) == 0.0
    assert np.max(np.abs(samples[beat // 2 : beat])) > 0.01
    assert np.max(np.abs(samples[beat + beat // 2 : 2 * beat])) > np.max(
        np.abs(samples[beat // 2 : beat])
    )
    assert bytes([0x90, 60, 45]) in midi
    assert bytes([0x90, 60, 120]) in midi


def test_pitch_bend_and_modulation_render_and_export_to_midi(
    project_script: Path,
) -> None:
    song = Project(
        "Controllers",
        prism_version="test",
        tempo=120,
        sample_rate=8_000,
        _script=project_script,
    )
    lead = song.track("Lead").midi(
        [Note("A4", start=0, duration=4, velocity=100)],
        bars=1,
        pitch_bend=[(0, 0), (1, 2), (3, -2), (4, 0)],
        modulation=[(0, 0), (2, 1), (4, 0)],
    )
    song.section("Only", bars=1, tracks=[lead])

    wav = song.render("renders/controllers.wav")
    midi = song.export_midi("renders/controllers.mid").path.read_bytes()
    flat = Project(
        "Flat",
        prism_version="test",
        tempo=120,
        sample_rate=8_000,
        _script=project_script,
    )
    flat_lead = flat.track("Lead").midi(
        [Note("A4", start=0, duration=4, velocity=100)], bars=1
    )
    flat.section("Only", bars=1, tracks=[flat_lead])
    flat_wav = flat.render("renders/flat.wav")

    assert wav.path.is_file()
    assert wav.path.read_bytes() != flat_wav.path.read_bytes()
    assert bytes([0xE0]) in midi
    assert bytes([0xB0, 1, 127]) in midi


def test_swing_and_seeded_humanization_are_resolved_reproducibly(
    project_script: Path,
) -> None:
    def resolved(seed: int) -> object:
        song = Project("Feel", prism_version="test", tempo=120, _script=project_script)
        song.track("Lead").midi(
            [
                Note("C4", start=0, duration=0.25, velocity=90),
                Note("E4", start=0.5, duration=0.25, velocity=90),
                Note("G4", start=1, duration=0.25, velocity=90),
            ],
            swing=0.66,
            humanize_timing_ms=8,
            humanize_velocity=5,
            humanize_seed=seed,
        )
        song.section("Only", bars=1)
        return _events(song)

    first = resolved(42)
    second = resolved(42)
    different = resolved(43)

    assert first == second
    assert first != different
    assert first[1]["start"] > 0.6  # type: ignore[index]
    assert 85 <= first[1]["velocity"] <= 95  # type: ignore[index]


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        ({"swing": 0.8}, "swing"),
        ({"humanize_timing_ms": 51}, "humanize_timing_ms"),
        ({"humanize_velocity": 31}, "humanize_velocity"),
        ({"pitch_bend": [(0, 3)]}, "Pitch bend"),
        ({"modulation": [(0, -0.1)]}, "Modulation"),
    ],
)
def test_expression_parameters_report_invalid_values(
    project_script: Path, arguments: dict[str, object], message: str
) -> None:
    song = Project("Invalid expression", prism_version="test", _script=project_script)

    with pytest.raises(ProjectError, match=message):
        song.track("Lead").midi("C4 -", **arguments)  # type: ignore[arg-type]
