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
        ("project_archive.py", True),
        ("cli_workflow.py", True),
        ("session_engine.py", False),
        ("offline_render.py", True),
        ("fake_backend.py", False),
        ("api_workflow.py", True),
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
