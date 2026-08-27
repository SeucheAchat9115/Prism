from __future__ import annotations

from pathlib import Path

import pytest

from prism import Project, ProjectError


def test_project_script_reads_like_a_song(project_script: Path) -> None:
    song = Project("Small Song", prism_version="test", tempo=105, _script=project_script)
    kick = song.track("Kick", gain_db=-2).drum("kick", "x--- x--- x--- x---")
    bass = song.track("Bass", pan=-0.2).midi(
        "C2 - C2 Eb2 | G1 - Bb1 -",
        instrument="bass",
        bars=2,
    )
    song.section("Intro", bars=2, tracks=[bass])
    song.section("Beat", bars=4, tracks=[kick, bass])

    summary = song.validate()
    configuration = song.configuration()

    assert str(summary) == "Small Song: 2 tracks, 2 sections, 6 bars, 13.71 seconds"
    assert configuration["tempo"] == 105.0
    assert configuration["sections"][1]["tracks"] == ("Kick", "Bass")
    assert configuration["tracks"][1]["part"]["kind"] == "midi"


def test_sections_can_include_every_track_implicitly(project_script: Path) -> None:
    song = Project("Loop", prism_version="test", _script=project_script)
    song.track("Kick").drum("kick", "x---")
    song.track("Lead").midi("C4 E4 G4 -")
    song.section("All", bars=1)

    assert song.validate().tracks == 2
    assert song.sections[0].tracks is None


def test_one_track_and_section_use_readable_singular_words(project_script: Path) -> None:
    song = Project("Solo", prism_version="test", _script=project_script)
    song.track("Lead").midi("C4")
    song.section("Only", bars=1)

    assert str(song.validate()) == "Solo: 1 track, 1 section, 1 bar, 2.00 seconds"


def test_project_reports_common_authoring_errors(project_script: Path) -> None:
    song = Project("Broken", prism_version="test", _script=project_script)
    song.track("Lead")
    with pytest.raises(ProjectError, match="already used"):
        song.track("lead")
    song.section("Verse", bars=1, tracks=["Missing"])
    with pytest.raises(ProjectError, match="has no sample"):
        song.validate()


@pytest.mark.parametrize("version", ("", "x" * 65))
def test_project_requires_a_readable_prism_version(
    project_script: Path, version: str
) -> None:
    with pytest.raises(ProjectError, match="Prism version"):
        Project("Versioned", prism_version=version, _script=project_script)


def test_tracks_accept_only_one_clear_part(project_script: Path) -> None:
    song = Project("One Part", prism_version="test", _script=project_script)
    track = song.track("Lead").midi("C4 -")
    with pytest.raises(ProjectError, match="already has content"):
        track.drum("kick", "x---")


def test_track_accepts_default_and_section_specific_clip_placements(
    project_script: Path,
) -> None:
    song = Project("Variations", prism_version="test", _script=project_script)
    kick = song.track("Kick").drum("kick", "x---")
    kick.drum("kick", "x-x-", section="Chorus")
    kick.drum(
        "kick",
        "xxxx",
        section="Chorus",
        start_bar=3,
        repeat=False,
    )
    song.section("Verse", bars=2, tracks=[kick])
    song.section("Chorus", bars=4, tracks=[kick])

    configuration = song.configuration()
    clips = configuration["tracks"][0]["clips"]  # type: ignore[index]

    assert song.validate().bars == 6
    assert len(kick.clips) == 3
    assert len(clips) == 3
    assert clips[1]["section"] == "Chorus"
    assert clips[2]["start_bar"] == 3.0
    assert clips[2]["repeat"] is False


def test_clip_placement_reports_unknown_sections_and_outside_starts(
    project_script: Path,
) -> None:
    unknown = Project("Unknown", prism_version="test", _script=project_script)
    unknown.track("Kick").drum("kick", "x---", section="Missing")
    unknown.section("Verse", bars=1)
    with pytest.raises(ProjectError, match="unknown section"):
        unknown.validate()

    outside = Project("Outside", prism_version="test", _script=project_script)
    outside.track("Kick").drum("kick", "x---", section="Verse", start_bar=1)
    outside.section("Verse", bars=1)
    with pytest.raises(ProjectError, match="outside section"):
        outside.validate()

    invalid = Project("Invalid", prism_version="test", _script=project_script)
    with pytest.raises(ProjectError, match="start_bar"):
        invalid.track("Kick").drum("kick", "x---", start_bar=-0.25)


def test_built_in_parts_reject_an_unsafe_duration_while_authoring(
    project_script: Path,
) -> None:
    song = Project("Long Part", prism_version="test", tempo=20, _script=project_script)

    with pytest.raises(ProjectError, match="cannot exceed 120 seconds"):
        song.track("Very Long Pad").midi("C3", instrument="pad", bars=11)


@pytest.mark.parametrize("path", ("../kick.wav", "C:/samples/kick.wav"))
def test_source_paths_must_stay_in_the_project(project_script: Path, path: str) -> None:
    song = Project("Safe Paths", prism_version="test", _script=project_script)
    with pytest.raises(ProjectError, match="relative"):
        song.track("Kick").sample(path)


def test_missing_sample_is_named_in_validation(project_script: Path) -> None:
    song = Project("Missing Sample", prism_version="test", _script=project_script)
    song.track("Kick").sample("sounds/kick.wav", "x---")
    song.section("Loop", bars=1)
    with pytest.raises(ProjectError, match="sounds.*kick.wav"):
        song.validate()
