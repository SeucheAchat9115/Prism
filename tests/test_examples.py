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
