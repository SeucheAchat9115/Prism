from __future__ import annotations

import runpy
import sys
from pathlib import Path

import pytest

from prism import PrismError
from prism.cli import create_project, main


def test_create_command_builds_a_runnable_plain_folder(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "first-beat"

    assert main(["create", str(target), "--name", "First Beat", "--tempo", "96"]) == 0

    assert target.is_dir()
    assert (target / "main.py").is_file()
    assert (target / "sounds").is_dir()
    assert (target / "renders").is_dir()
    assert not list(tmp_path.glob("*.zip"))
    assert "Created Prism project" in capsys.readouterr().out

    runpy.run_path(str(target / "main.py"), run_name="__main__")

    assert (target / "renders" / "song.wav").is_file()
    assert (target / "renders" / "song.mid").is_file()
    assert (target / ".prism" / "project.json").is_file()


def test_create_uses_a_readable_name_from_the_folder(tmp_path: Path) -> None:
    target = create_project(tmp_path / "late_night-groove")

    assert "'Late Night Groove'" in (target / "main.py").read_text(encoding="utf-8")


def test_create_never_overwrites_an_existing_folder(tmp_path: Path) -> None:
    target = tmp_path / "existing"
    target.mkdir()

    with pytest.raises(PrismError, match="already exists"):
        create_project(target)


def test_cli_reports_existing_folder_as_a_usage_error(tmp_path: Path) -> None:
    target = tmp_path / "existing"
    target.mkdir()

    with pytest.raises(SystemExit, match="2"):
        main(["create", str(target)])


def test_cli_without_a_command_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    assert "prism create" in capsys.readouterr().out


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
        create_project(tmp_path / "song", name=name)


@pytest.mark.parametrize("tempo", (19.9, 300.1))
def test_create_rejects_an_invalid_tempo(tmp_path: Path, tempo: float) -> None:
    with pytest.raises(PrismError, match="between 20 and 300"):
        create_project(tmp_path / "song", tempo=tempo)
