"""Exercise the Phase 6 CLI against one explicit foreground project service."""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import httpx
from _support import parse_output_dir, write_sine_wav


def run_cli(*arguments: str | Path) -> dict[str, Any]:
    """Run the installed CLI, print its streams, and parse one JSON envelope."""

    command = [sys.executable, "-m", "vibesound", *(str(argument) for argument in arguments)]
    print(f"$ {subprocess.list2cmdline(command)}")
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    if result.returncode != 0:
        raise RuntimeError(f"CLI command failed with exit code {result.returncode}")
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    return cast(dict[str, Any], json.loads(lines[-1]))


@contextmanager
def running_service(project: Path) -> Iterator[str]:
    """Start the real ``vibesound serve`` command and stop it gracefully."""

    with socket.create_server(("127.0.0.1", 0)) as reservation:
        port = int(reservation.getsockname()[1])
    url = f"http://127.0.0.1:{port}"
    command = [
        sys.executable,
        "-m",
        "vibesound",
        "serve",
        str(project),
        "--port",
        str(port),
        "--json",
    ]
    print(f"$ {subprocess.list2cmdline(command)}")
    creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    process = subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creation_flags,
    )
    deadline = time.monotonic() + 15.0
    try:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(
                    f"Service exited during startup with code {process.returncode}"
                )
            try:
                response = httpx.get(f"{url}/api/v1/readiness", timeout=0.25)
            except httpx.HTTPError:
                time.sleep(0.05)
                continue
            if response.status_code == 200:
                break
            time.sleep(0.05)
        else:
            raise RuntimeError("VibeSound service did not become ready")
        yield url
    finally:
        if process.poll() is None:
            if os.name == "nt":
                process.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                process.send_signal(signal.SIGINT)
        try:
            process.wait(timeout=10.0)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5.0)


def _service_args(url: str) -> tuple[str, ...]:
    return ("--url", url, "--json")


def main() -> int:
    run_dir = parse_output_dir(
        "cli-workflow",
        "Run the complete VibeSound Phase 6 CLI workflow.",
    )
    project_path = run_dir / "cli-example.vibesound-work"
    source_path = run_dir / "cli-source.wav"
    operations_path = run_dir / "operations.json"
    render_commands_path = run_dir / "render-commands.json"
    write_sine_wav(source_path, sample_rate=8000, seconds=0.5, frequency=330.0)

    run_cli("doctor", "--json")
    run_cli("version", "--json")
    run_cli(
        "project",
        "init",
        project_path,
        "--name",
        "CLI Example",
        "--sample-rate",
        "8000",
        "--json",
    )
    run_cli("serve", project_path, "--dry-run", "--json")

    with running_service(project_path) as url:
        service = _service_args(url)
        run_cli("server", "status", project_path, *service)
        run_cli("server", "capabilities", project_path, *service)
        run_cli("server", "schemas", project_path, *service)
        run_cli("project", "show", project_path, *service)
        run_cli("project", "validate", project_path, *service)
        run_cli("project", "state", project_path, *service)
        run_cli("audio", "devices", project_path, *service)
        run_cli("audio", "restart", project_path, "--dry-run", *service)

        run_cli("audio", "import", project_path, source_path, "--dry-run", *service)
        imported = run_cli(
            "asset",
            "import",
            project_path,
            source_path,
            "--idempotency-key",
            "phase6-example-import",
            *service,
        )
        asset_id = imported["data"]["asset_id"]
        track_id, scene_id, clip_id = (uuid4(), uuid4(), uuid4())
        operations_path.write_text(
            json.dumps(
                [
                    {"op": "track.create", "track_id": str(track_id), "name": "Lead"},
                    {"op": "scene.create", "scene_id": str(scene_id), "name": "Verse"},
                    {
                        "op": "clip.create",
                        "clip_id": str(clip_id),
                        "name": "Tone",
                        "asset_id": asset_id,
                        "loop": True,
                    },
                    {
                        "op": "slot.assign",
                        "track_id": str(track_id),
                        "scene_id": str(scene_id),
                        "clip_id": str(clip_id),
                    },
                ],
                indent=2,
            ),
            encoding="utf-8",
        )
        run_cli("transaction", "preview", project_path, operations_path, *service)
        run_cli("transaction", "commit", project_path, operations_path, *service)
        run_cli("entity", "list", project_path, "track", *service)
        run_cli("entity", "resolve", project_path, "track", "lead", *service)

        run_cli(
            "session",
            "launch",
            project_path,
            "--track",
            "lead",
            "--scene",
            "verse",
            "--dry-run",
            *service,
        )
        run_cli(
            "session",
            "launch",
            project_path,
            "--track",
            "lead",
            "--scene",
            "verse",
            *service,
        )
        run_cli("session", "stop", project_path, "--track", "lead", "--dry-run", *service)
        run_cli("session", "stop", project_path, "--track", "lead", *service)

        run_cli("transport", "play", project_path, "--dry-run", *service)
        run_cli("transport", "play", project_path, *service)
        run_cli("transport", "pause", project_path, *service)
        run_cli("transport", "stop", project_path, *service)
        run_cli("transport", "reset", project_path, *service)

        render_commands_path.write_text(
            json.dumps(
                [
                    {
                        "frame": 0,
                        "operation": "launch_scene",
                        "scene_id": str(scene_id),
                    }
                ],
                indent=2,
            ),
            encoding="utf-8",
        )
        run_cli(
            "render",
            project_path,
            "--seconds",
            "0.1",
            "--commands",
            render_commands_path,
            "--dry-run",
            *service,
        )
        rendered = run_cli(
            "render",
            project_path,
            "--seconds",
            "0.1",
            "--commands",
            render_commands_path,
            "--output",
            "cli-example.wav",
            *service,
        )
        job_id = rendered["data"]["job_id"]
        run_cli("job", "list", project_path, *service)
        run_cli("job", "show", project_path, job_id, *service)
        run_cli("job", "wait", project_path, job_id, *service)
        run_cli("job", "cancel", project_path, job_id, "--dry-run", *service)

        run_cli(
            "project",
            "export",
            project_path,
            "--output",
            "cli-example.vibesound",
            "--dry-run",
            *service,
        )
        exported = run_cli(
            "project",
            "export",
            project_path,
            "--output",
            "cli-example.vibesound",
            *service,
        )
        run_cli("project", "detach-source", project_path, "--dry-run", *service)

    portable = Path(exported["data"]["output_path"])
    run_cli("project", "show", portable, "--portable", "--json")
    run_cli("project", "validate", portable, "--portable", "--json")
    run_cli("project", "migrate", portable, "--dry-run", "--json")
    print(f"CLI example output: {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
