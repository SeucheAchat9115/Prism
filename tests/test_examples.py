from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


@pytest.mark.parametrize(
    ("script", "needs_output_dir"),
    (
        ("01_project_archive.py", True),
        ("02_make_beat.py", True),
        ("03_session_performance.py", True),
        ("04_render_song.py", True),
        ("05_cli_agent_workflow.py", True),
        ("06_transaction_safety.py", True),
        ("07_api_client.py", True),
        ("08_backend_comparison.py", True),
        ("10_agent_producer_workflow.py", True),
        ("14_native_synth_song.py", True),
    ),
)
def test_device_free_examples_run(
    tmp_path: Path,
    script: str,
    needs_output_dir: bool,
) -> None:
    command = [sys.executable, str(EXAMPLES / script)]
    if needs_output_dir:
        command.extend(("--output-dir", str(tmp_path / Path(script).stem)))
    result = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"


def test_audio_device_diagnostic_help_is_available() -> None:
    result = subprocess.run(
        [sys.executable, str(EXAMPLES / "09_audio_device_diagnostics.py"), "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "--play-seconds" in result.stdout


def test_browser_session_example_help_is_available() -> None:
    commands = (
        ("11_browser_session.py", "--no-open"),
        ("12_reproducible_poc.py", "--app-python"),
    )
    for script, expected_option in commands:
        result = subprocess.run(
            [sys.executable, str(EXAMPLES / script), "--help"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        assert expected_option in result.stdout


def test_vst3_example_help_is_available_without_a_plugin() -> None:
    result = subprocess.run(
        [sys.executable, str(EXAMPLES / "13_vst3_effect.py"), "--help"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert "--plugin" in result.stdout
    assert "--registry-id" in result.stdout


def test_markdown_tutorial_curriculum_has_every_level_and_copyable_commands() -> None:
    tutorial_root = EXAMPLES / "tutorials"
    expected = {
        "00-listen-to-the-demo.md": ("prism demo", "transport play", "Start-Process"),
        "01-make-one-synth-sound.md": ("synth generate", "clip.create", "session launch"),
        "02-build-a-drum-loop.md": ("--preset kick", "--preset snare", "--preset hihat"),
        "03-build-a-mini-song.md": ("--preset bass", "--preset pad", "launch_scene"),
        "04-shape-mix-and-edit.md": ("clip.update", "--dry-run", "stale_revision"),
        "05-control-with-python.md": ("PrismClient", "SynthAssetRequest", "wait_for_job"),
        "06-perform-in-the-browser.md": ("events watch", "Preview & render", "job list"),
        "07-add-a-vst3-effect.md": ("plugin trust", "plugin attach", "offline renders"),
        "08-toolbox-map.md": ("prism --help", "audio devices", "14_native_synth_song.py"),
    }
    index = (tutorial_root / "README.md").read_text(encoding="utf-8")
    for name, milestones in expected.items():
        path = tutorial_root / name
        assert path.is_file()
        assert f"]({name})" in index
        content = path.read_text(encoding="utf-8")
        assert "```powershell" in content
        for milestone in milestones:
            assert milestone in content
    assert "14_native_synth_song.py" in index
