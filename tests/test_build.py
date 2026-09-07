
from __future__ import annotations

import json
from pathlib import Path

import pytest
from tutorial_harness import run_contract_tutorial

from prism import (
    Project,
    ProjectError,
    build_project,
    doctor_project,
    resolve_project_root,
)
from prism.cli import create_project, main


def test_new_scaffold_build_has_no_export_side_effect(tmp_path: Path) -> None:
    target = create_project(
        "clean-build", _root=tmp_path, _timestamp="20260906-120000"
    )

    project = build_project(target)

    assert project.name == "Clean Build"
    assert list((target / "renders").iterdir()) == []


def test_explicit_project_root_works_from_another_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "notebook-song"
    root.mkdir()
    (root / "main.py").write_text("# notebook source\n", encoding="utf-8")
    other = tmp_path / "elsewhere"
    other.mkdir()
    monkeypatch.chdir(other)

    project = Project(
        "Notebook Song",
        prism_version="0.2.0.dev0",
        project_root=root,
    )

    assert project.root == root.resolve()
    assert project.script == (root / "main.py").resolve()
    assert resolve_project_root(root / "main.py") == root.resolve()


def test_render_rejects_legacy_top_level_exports_with_migration_message(
    tmp_path: Path,
) -> None:
    root = tmp_path / "legacy"
    root.mkdir()
    (root / "main.py").write_text(
        'from prism import Project\n'
        'song = Project("Legacy", prism_version="0.2.0.dev0")\n'
        'song.render("renders/song.wav")\n',
        encoding="utf-8",
    )

    with pytest.raises(ProjectError, match="build"):
        build_project(root)


def test_render_command_uses_build_contract_and_profile(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = create_project(
        "cli-render", _root=tmp_path, _timestamp="20260906-120001"
    )

    assert main(
        [
            "render",
            str(target),
            "--output",
            "renders/cli.wav",
            "--profile",
            "master",
        ]
    ) == 0

    assert (target / "renders" / "cli.wav").is_file()
    output = capsys.readouterr().out
    assert "Rendered" in output
    assert "SHA-256:" in output


def test_doctor_is_metadata_only_by_default(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "unsafe-to-run"
    root.mkdir()
    (root / "main.py").write_text(
        "raise RuntimeError('doctor must not execute this source')\n",
        encoding="utf-8",
    )

    assert main(["doctor", str(root)]) == 0
    output = capsys.readouterr().out
    assert "metadata" in output.lower()
    assert "RuntimeError" not in output


def test_doctor_build_validation_is_structured(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = create_project(
        "doctor-build", _root=tmp_path, _timestamp="20260906-120002"
    )

    assert main(["doctor", str(target), "--build", "--json"]) == 0

    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "ok"
    assert report["build"]["status"] == "ok"
    assert list((target / "renders").iterdir()) == []


def test_doctor_native_projects_do_not_require_optional_vst_host(tmp_path: Path) -> None:
    target = create_project(
        "native-doctor", _root=tmp_path, _timestamp="20260906-120003"
    )

    report = doctor_project(target)

    assert report["status"] in {"ok", "warning"}
    assert report["plugins"]["status"] == "ok"


def test_existing_delay_guide_uses_canonical_time_beats() -> None:
    document = Path("docs/guides/mixing-and-automation.md").read_text(encoding="utf-8")

    assert "time_beats" in document
    assert "delay_beats" not in document


def test_build_contract_tutorial_is_harnessed_without_render_side_effect(
    tmp_path: Path,
) -> None:
    root = tmp_path / "tutorial-project"

    project = run_contract_tutorial(
        Path("docs/tutorial/23-build-contract-and-doctor.md"),
        root,
    )

    assert not (root / "renders").exists()
    project.render("renders/tutorial.wav")
    assert (root / "renders" / "tutorial.wav").is_file()
