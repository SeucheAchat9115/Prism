from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from prism.cli import app


def test_portable_project_cli_workflow_uses_versioned_envelopes(tmp_path: Path) -> None:
    runner = CliRunner()
    project_path = tmp_path / "cli-demo.prism"

    initialized = runner.invoke(
        app,
        ["project", "init", str(project_path), "--name", "CLI Demo", "--json"],
    )
    validated = runner.invoke(
        app,
        ["project", "validate", str(project_path), "--portable", "--json"],
    )
    shown = runner.invoke(
        app,
        ["project", "show", str(project_path), "--portable", "--json"],
    )

    assert initialized.exit_code == 0, initialized.stdout
    assert validated.exit_code == 0, validated.stdout
    assert shown.exit_code == 0, shown.stdout
    initialized_json = json.loads(initialized.stdout)
    validated_json = json.loads(validated.stdout)
    shown_json = json.loads(shown.stdout)
    assert initialized_json["cli_schema_version"] == 1
    assert initialized_json["command"] == "project init"
    assert validated_json["ok"] is True
    assert validated_json["data"]["ok"] is True
    assert shown_json["data"]["name"] == "CLI Demo"


def test_project_init_dry_run_does_not_create_output(tmp_path: Path) -> None:
    path = tmp_path / "dry.prism-work"
    result = CliRunner().invoke(
        app,
        ["project", "init", str(path), "--dry-run", "--json"],
    )

    assert result.exit_code == 0, result.stdout
    assert json.loads(result.stdout)["dry_run"] is True
    assert not path.exists()


def test_serve_dry_run_renders_a_valid_ipv6_url(tmp_path: Path) -> None:
    project_path = tmp_path / "ipv6.prism-work"
    initialized = CliRunner().invoke(
        app,
        ["project", "init", str(project_path), "--json"],
    )
    assert initialized.exit_code == 0, initialized.stdout

    result = CliRunner().invoke(
        app,
        ["serve", str(project_path), "--host", "::1", "--dry-run", "--json"],
    )

    assert result.exit_code == 0, result.stdout
    assert json.loads(result.stdout)["data"]["url"] == "http://[::1]:8765"
