from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from vibesound.cli import app
from vibesound.project import ProjectRepository


def test_one_command_demo_is_device_free_and_reopenable(tmp_path: Path) -> None:
    path = tmp_path / "demo.vibesound-work"
    runner = CliRunner()

    created = runner.invoke(app, ["demo", str(path), "--no-serve"])
    reopened = runner.invoke(app, ["demo", str(path), "--no-serve"])

    assert created.exit_code == 0, created.output
    assert reopened.exit_code == 0, reopened.output
    with ProjectRepository.open(path) as repository:
        project = repository.get_project()
        assert project.revision.number == 1
        assert len(project.tracks) == 2
        assert len(project.scenes) == 2
        assert len(project.assets) == 2
        assert len(project.clips) == 2
