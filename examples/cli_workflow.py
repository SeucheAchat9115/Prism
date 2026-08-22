"""Exercise the Phase 1 CLI against a generated project and audio asset."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from _support import parse_output_dir, write_sine_wav


def run_cli(*arguments: str | Path) -> None:
    """Run the installed CLI using the same Python environment as this example."""

    command = [sys.executable, "-m", "vibesound", *(str(argument) for argument in arguments)]
    print(f"$ {subprocess.list2cmdline(command)}")
    subprocess.run(command, check=True)


def main() -> int:
    run_dir = parse_output_dir(
        "cli-workflow",
        "Run the currently available VibeSound CLI commands.",
    )
    project_path = run_dir / "cli-example.vibesound"
    source_path = run_dir / "cli-source.wav"
    write_sine_wav(source_path, sample_rate=8000, seconds=0.5, frequency=330.0)

    run_cli(
        "project",
        "init",
        project_path,
        "--name",
        "CLI Example",
        "--sample-rate",
        "8000",
    )
    run_cli("project", "show", project_path, "--json")
    run_cli("project", "validate", project_path, "--json")
    run_cli("asset", "import", project_path, source_path, "--json")
    run_cli("project", "show", project_path, "--json")
    run_cli("project", "migrate", project_path)
    print(f"CLI example output: {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
