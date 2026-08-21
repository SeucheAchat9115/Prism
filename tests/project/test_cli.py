from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from vibesound.cli import app

from ._helpers import write_wav


def test_project_cli_workflow(tmp_path: Path) -> None:
    runner = CliRunner()
    project_path = tmp_path / "cli-demo.vibesound"
    source_path = tmp_path / "sample.wav"
    write_wav(source_path)

    initialized = runner.invoke(
        app,
        ["project", "init", str(project_path), "--name", "CLI Demo"],
    )
    imported = runner.invoke(
        app,
        ["asset", "import", str(project_path), str(source_path), "--json"],
    )
    validated = runner.invoke(app, ["project", "validate", str(project_path), "--json"])
    shown = runner.invoke(app, ["project", "show", str(project_path), "--json"])

    assert initialized.exit_code == 0, initialized.stdout
    assert imported.exit_code == 0, imported.stdout
    assert validated.exit_code == 0, validated.stdout
    assert shown.exit_code == 0, shown.stdout
    assert json.loads(imported.stdout)["kind"] == "audio"
    assert json.loads(validated.stdout)["ok"] is True
    assert json.loads(shown.stdout)["name"] == "CLI Demo"
