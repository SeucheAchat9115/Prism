from __future__ import annotations

import runpy
import sys
from pathlib import Path

import pytest

from prism import PrismError
from prism.cli import create_project, main


def test_create_command_builds_a_runnable_plain_folder(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)

    assert main(["create", "first-beat", "--name", "First Beat", "--tempo", "96"]) == 0

    projects = tmp_path / "projects"
    matches = list(projects.glob("first-beat-????????-??????"))
    assert len(matches) == 1
    target = matches[0]

    assert projects.is_dir()
    assert target.is_dir()
    assert (target / "main.py").is_file()
    assert (target / "sounds").is_dir()
    assert (target / "renders").is_dir()
    assert (target / "plugin-states").is_dir()
    assert (target / "vst.json").is_file()
    command_output = capsys.readouterr().out
    assert "Created Prism project" in command_output
    assert 'Run it with: uv run "' in command_output
    assert 'projects/first-beat-' in command_output
    assert '/main.py\"' in command_output
    source = (target / "main.py").read_text(encoding="utf-8")
    assert "__file__" not in source
    assert 'prism_version="0.2.0.dev0"' in source

    runpy.run_path(str(target / "main.py"), run_name="__main__")

    assert (target / "renders" / "song.wav").is_file()
    assert (target / "renders" / "song.mid").is_file()


def test_create_uses_a_readable_name_from_the_folder(tmp_path: Path) -> None:
    target = create_project(
        "late_night-groove", _root=tmp_path, _timestamp="20260827-123456"
    )

    assert '"Late Night Groove"' in (target / "main.py").read_text(encoding="utf-8")
    assert target == tmp_path / "projects" / "late_night-groove-20260827-123456"


def test_tutorial_option_creates_a_timestamped_starting_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)

    assert main(["create", "--tutorial"]) == 0

    matches = list((tmp_path / "projects").glob("tutorial-????????-??????"))
    assert len(matches) == 1
    source = (matches[0] / "main.py").read_text(encoding="utf-8")
    assert '"Prism Tutorial"' in source
    assert "Tutorial guide: docs/tutorial/README.md" in capsys.readouterr().out


def test_create_requires_a_name_unless_tutorial_is_requested(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit, match="2"):
        main(["create"])
    assert "Give the project a name or use --tutorial" in capsys.readouterr().err


def test_create_never_overwrites_an_existing_folder(tmp_path: Path) -> None:
    create_project("existing", _root=tmp_path, _timestamp="20260827-123456")

    with pytest.raises(PrismError, match="already exists"):
        create_project("existing", _root=tmp_path, _timestamp="20260827-123456")


@pytest.mark.parametrize("folder", ("nested/song", "../song"))
def test_create_accepts_a_name_not_a_path(tmp_path: Path, folder: str) -> None:
    with pytest.raises(PrismError, match="folder name, not a path"):
        create_project(folder, _root=tmp_path)


def test_cli_without_a_command_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    assert "prism create" in capsys.readouterr().out


def test_samples_command_lists_audio_without_running_project(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = tmp_path / "project"
    (project / "sounds" / "drums").mkdir(parents=True)
    (project / "recordings").mkdir()
    (project / "renders").mkdir()
    (project / "main.py").write_text(
        "raise RuntimeError('must not execute')\n", encoding="utf-8"
    )
    (project / "sounds" / "drums" / "kick.wav").write_bytes(b"sample")
    (project / "recordings" / "phrase.aiff").write_bytes(b"sample")
    (project / "renders" / "song.wav").write_bytes(b"generated")

    assert main(["samples", str(project)]) == 0
    output = capsys.readouterr().out

    assert "sounds/drums/kick.wav" in output
    assert "recordings/phrase.aiff" in output
    assert "renders/song.wav" not in output
    assert "Every filename is unique" in output
    assert "register other folders" in output


def test_samples_command_reports_duplicate_filenames(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = tmp_path / "project"
    (project / "sounds" / "one").mkdir(parents=True)
    (project / "sounds" / "two").mkdir()
    (project / "main.py").write_text("# song\n", encoding="utf-8")
    (project / "sounds" / "one" / "kick.wav").write_bytes(b"one")
    (project / "sounds" / "two" / "kick.wav").write_bytes(b"two")

    assert main(["samples", str(project / "main.py")]) == 0
    output = capsys.readouterr().out

    assert "Duplicate filenames" in output
    assert "sounds/one/kick.wav" in output
    assert "sounds/two/kick.wav" in output


def test_samples_command_requires_a_project_folder(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit, match="2"):
        main(["samples", str(tmp_path)])
    assert "containing main.py" in capsys.readouterr().err


def test_python_module_entry_point_prints_help(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["prism"])
    with pytest.raises(SystemExit, match="0"):
        runpy.run_module("prism", run_name="__main__")
    assert "prism create" in capsys.readouterr().out


@pytest.mark.parametrize("name", ("   ", "x" * 121))
def test_create_rejects_an_invalid_name(tmp_path: Path, name: str) -> None:
    with pytest.raises(PrismError, match="name"):
        create_project("song", name=name, _root=tmp_path)


@pytest.mark.parametrize("tempo", (19.9, 300.1))
def test_create_rejects_an_invalid_tempo(tmp_path: Path, tempo: float) -> None:
    with pytest.raises(PrismError, match="between 20 and 300"):
        create_project("song", tempo=tempo, _root=tmp_path)


def test_create_rejects_an_invalid_internal_timestamp(tmp_path: Path) -> None:
    with pytest.raises(PrismError, match="timestamp"):
        create_project("song", _root=tmp_path, _timestamp="today")
