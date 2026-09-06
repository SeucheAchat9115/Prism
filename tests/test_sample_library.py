from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from prism import Project, ProjectError, SampleLibrary


def _write_sample(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, np.linspace(0.5, 0.0, 400, dtype=np.float32), 8_000)


def test_default_library_finds_nested_sample_by_short_name(project_script: Path) -> None:
    sample = project_script.parent / "sounds" / "drums" / "kick-heavy.wav"
    _write_sample(sample)
    song = Project(
        "Short Samples",
        prism_version="test",
        tempo=300,
        sample_rate=8_000,
        _script=project_script,
    )

    kick = song.track("Kick").sample("kick-heavy.wav", "x---")
    song.section("Loop", bars=1, tracks=[kick])
    configuration = song.configuration()

    assert isinstance(song.samples, SampleLibrary)
    assert song.samples.folders == ("sounds",)
    assert song.samples.files() == ("sounds/drums/kick-heavy.wav",)
    assert configuration["schema_version"] == 8
    assert configuration["sample_folders"] == ("sounds",)
    assert configuration["tracks"][0]["part"]["path"] == "sounds/drums/kick-heavy.wav"  # type: ignore[index]
    assert song.render().path.is_file()


def test_additional_sample_folder_is_searchable(project_script: Path) -> None:
    sample = project_script.parent / "recordings" / "vocals" / "phrase.wav"
    _write_sample(sample)
    song = Project("Folders", prism_version="test", _script=project_script)

    returned = song.samples.add_folder("recordings")
    song.samples.add_folder("recordings")

    assert returned is song.samples
    assert song.samples.folders == ("sounds", "recordings")
    assert song.samples.find("phrase.wav") == "recordings/vocals/phrase.wav"


def test_duplicate_short_names_require_an_explicit_path(project_script: Path) -> None:
    _write_sample(project_script.parent / "sounds" / "acoustic" / "kick.wav")
    _write_sample(project_script.parent / "sounds" / "electronic" / "kick.wav")
    song = Project("Duplicates", prism_version="test", _script=project_script)

    with pytest.raises(ProjectError, match="ambiguous.*sounds/acoustic/kick.wav"):
        song.samples.find("kick.wav")

    assert song.samples.find("sounds/electronic/kick.wav") == (
        "sounds/electronic/kick.wav"
    )


def test_missing_short_name_suggests_the_closest_sample(project_script: Path) -> None:
    _write_sample(project_script.parent / "sounds" / "kick-heavy.wav")
    song = Project("Suggestions", prism_version="test", _script=project_script)

    with pytest.raises(ProjectError, match="Did you mean 'kick-heavy.wav'"):
        song.samples.find("kik-heavy.wav")


def test_explicit_missing_path_is_reported_during_validation(project_script: Path) -> None:
    song = Project("Missing", prism_version="test", _script=project_script)
    song.track("Kick").sample("sounds/missing.wav")
    song.section("Loop", bars=1)

    with pytest.raises(ProjectError, match="sounds.*missing.wav"):
        song.validate()


@pytest.mark.parametrize("folder", ("../library", "C:/library", "/library"))
def test_sample_folders_must_stay_inside_project(
    project_script: Path, folder: str
) -> None:
    song = Project("Safe Folders", prism_version="test", _script=project_script)

    with pytest.raises(ProjectError, match="relative"):
        song.samples.add_folder(folder)


def test_registered_sample_folder_must_exist(project_script: Path) -> None:
    song = Project("Missing Folder", prism_version="test", _script=project_script)

    with pytest.raises(ProjectError, match="does not exist"):
        song.samples.add_folder("recordings")
