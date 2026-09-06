from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from prism import Project, ProjectError, Track


def _peak(song: Project, output: str) -> float:
    samples, _ = sf.read(song.render(output).path, dtype="float64", always_2d=True)
    return float(np.max(np.abs(samples)))


def _kick_song(script: Path, name: str) -> tuple[Project, Track]:
    song = Project(
        name,
        prism_version="test",
        tempo=120,
        sample_rate=8_000,
        master_gain_db=-12,
        normalize=False,
        _script=script,
    )
    kick = song.track("Kick", gain_db=-12).drum("kick", "x---")
    song.section("Only", bars=1, tracks=[kick])
    return song, kick


def test_group_bus_replaces_direct_route(project_script: Path) -> None:
    direct, _ = _kick_song(project_script, "Direct")
    grouped, kick = _kick_song(project_script, "Grouped")
    grouped.bus("Drums", tracks=[kick], gain_db=-12)

    direct_peak = _peak(direct, "renders/direct.wav")
    grouped_peak = _peak(grouped, "renders/grouped.wav")

    assert grouped_peak == pytest.approx(direct_peak * 10.0 ** (-12.0 / 20.0), rel=0.01)


def test_send_adds_parallel_return_without_removing_direct_signal(
    project_script: Path,
) -> None:
    direct, _ = _kick_song(project_script, "Direct")
    parallel, kick = _kick_song(project_script, "Parallel")
    room = parallel.bus("Room")
    kick.send(room, gain_db=0)

    direct_peak = _peak(direct, "renders/direct-send.wav")
    parallel_peak = _peak(parallel, "renders/parallel.wav")

    assert parallel_peak == pytest.approx(direct_peak * 2.0, rel=0.01)


def test_master_effect_processes_the_complete_mix(project_script: Path) -> None:
    direct, _ = _kick_song(project_script, "Direct")
    mastered, _ = _kick_song(project_script, "Mastered")
    mastered.master_effect("gain", name="Master Trim", gain_db=-6)

    direct_peak = _peak(direct, "renders/direct-master.wav")
    mastered_peak = _peak(mastered, "renders/mastered.wav")

    assert mastered_peak == pytest.approx(direct_peak * 10.0 ** (-6.0 / 20.0), rel=0.01)


def test_bus_send_master_configuration_and_automation_are_inspectable(
    project_script: Path,
) -> None:
    song, kick = _kick_song(project_script, "Mixer")
    drums = song.bus("Drums", tracks=[kick], gain_db=-2)
    compressor = drums.effect("compressor", name="Glue", threshold_db=-20, ratio=3)
    room = song.bus("Room", gain_db=-6)
    kick.send(room, gain_db=-14)
    room.effect("reverb", mix=1)
    limiter = song.master_effect("compressor", name="Master Control", threshold_db=-6)
    song.automation(
        "Bus Threshold",
        target=compressor,
        parameter="threshold_db",
        points=[(0, -24), (1, -12)],
    )
    song.automation(
        "Master Mix",
        target=limiter,
        parameter="mix",
        points=[(0, 0), (1, 1)],
    )

    configuration = song.configuration()
    track = configuration["tracks"][0]  # type: ignore[index]
    buses = configuration["buses"]  # type: ignore[assignment]

    assert configuration["schema_version"] == 11
    assert track["output_bus"] == "Drums"  # type: ignore[index]
    assert track["sends"][0]["bus"] == "Room"  # type: ignore[index]
    assert buses[0]["effects"][0]["name"] == "Glue"  # type: ignore[index]
    assert configuration["master_effects"][0]["name"] == "Master Control"  # type: ignore[index]
    assert song.render("renders/mixer.wav").path.is_file()


def test_mixer_routing_errors_are_specific(project_script: Path, tmp_path: Path) -> None:
    song, kick = _kick_song(project_script, "Routing")
    drums = song.bus("Drums", tracks=[kick])
    other_script = tmp_path / "other.py"
    other_script.write_text("# test\n", encoding="utf-8")
    other = Project("Other", prism_version="test", _script=other_script)
    foreign = other.track("Foreign").drum("kick", "x---")
    foreign_bus = other.bus("Foreign Bus")

    with pytest.raises(ProjectError, match="same project"):
        drums.add(foreign)
    with pytest.raises(ProjectError, match="same project"):
        kick.send(foreign_bus)
    with pytest.raises(ProjectError, match="already routes"):
        song.bus("Second Group", tracks=[kick])
    with pytest.raises(ProjectError, match="would duplicate"):
        kick.send(drums)
