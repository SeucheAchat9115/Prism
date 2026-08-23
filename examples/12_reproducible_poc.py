"""Run the complete Phase 8 POC against one selected VibeSound installation."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4, uuid5

import httpx
import soundfile as sf
from playwright.sync_api import Page, expect, sync_playwright


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the browser, CLI, transaction, render, and reopen POC acceptance flow."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "output",
        help="Base directory for a unique acceptance run directory.",
    )
    parser.add_argument(
        "--app-python",
        type=Path,
        default=Path(sys.executable),
        help="Python interpreter containing the VibeSound installation under test.",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Show Chromium instead of running headlessly.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Seconds allowed for each service, CLI, and browser operation.",
    )
    return parser.parse_args()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _new_run_directory(base: Path) -> Path:
    run_directory = base.expanduser().resolve(strict=False) / (
        f"phase8-poc-{datetime.now():%Y%m%d-%H%M%S}-{uuid4().hex[:6]}"
    )
    run_directory.mkdir(parents=True, exist_ok=False)
    return run_directory


def _append_log(path: Path, *lines: str) -> None:
    with path.open("a", encoding="utf-8") as output:
        for line in lines:
            output.write(line)
            if not line.endswith("\n"):
                output.write("\n")


def _run_cli(
    app_python: Path,
    run_directory: Path,
    log_path: Path,
    *arguments: str | Path,
    timeout: float,
    expect_success: bool = True,
) -> dict[str, Any]:
    command = [
        str(app_python),
        "-m",
        "vibesound",
        *(str(argument) for argument in arguments),
        "--json",
    ]
    result = subprocess.run(
        command,
        cwd=run_directory,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    _append_log(
        log_path,
        f"$ {subprocess.list2cmdline(command)}",
        result.stdout,
        result.stderr,
        f"exit={result.returncode}",
    )
    if expect_success and result.returncode != 0:
        raise RuntimeError(
            f"CLI command failed with exit code {result.returncode}: "
            f"{subprocess.list2cmdline(command)}\n{result.stdout}\n{result.stderr}"
        )
    if not expect_success and result.returncode == 0:
        rendered_command = subprocess.list2cmdline(command)
        raise RuntimeError(f"CLI command unexpectedly succeeded: {rendered_command}")
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError(f"CLI command did not emit its JSON envelope: {command}")
    payload = json.loads(lines[-1])
    if not isinstance(payload, dict):
        raise RuntimeError(f"CLI command returned a non-object JSON envelope: {payload!r}")
    return cast(dict[str, Any], payload)


def _reserve_port() -> int:
    with socket.create_server(("127.0.0.1", 0)) as reservation:
        return int(reservation.getsockname()[1])


@contextmanager
def _running_service(
    app_python: Path,
    project_path: Path,
    run_directory: Path,
    log_path: Path,
    timeout: float,
) -> Iterator[str]:
    port = _reserve_port()
    url = f"http://127.0.0.1:{port}"
    command = [
        str(app_python),
        "-m",
        "vibesound",
        "serve",
        str(project_path),
        "--port",
        str(port),
        "--json",
    ]
    creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    _append_log(log_path, f"$ {subprocess.list2cmdline(command)}")
    with log_path.open("a", encoding="utf-8") as service_output:
        process = subprocess.Popen(
            command,
            cwd=run_directory,
            stdout=service_output,
            stderr=subprocess.STDOUT,
            text=True,
            creationflags=creation_flags,
        )
        try:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(
                        f"VibeSound service exited during startup with code {process.returncode}"
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
                raise RuntimeError(f"VibeSound service did not become ready at {url}")
            yield url
        finally:
            if process.poll() is None:
                process.send_signal(
                    signal.CTRL_BREAK_EVENT if os.name == "nt" else signal.SIGINT
                )
            try:
                process.wait(timeout=10.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5.0)
            service_output.write(f"service-exit={process.returncode}\n")


def _demo_ids(project_id: str) -> dict[str, str]:
    namespace = UUID(project_id)
    names = (
        "drums",
        "synth",
        "verse",
        "chorus",
        "kick-asset",
        "tone-asset",
        "kick-clip",
        "tone-clip",
        "kick-slot",
        "tone-slot",
        "chorus-kick-clip",
        "chorus-tone-clip",
        "chorus-kick-slot",
        "chorus-tone-slot",
    )
    return {name: str(uuid5(namespace, f"vibesound-demo:{name}")) for name in names}


def _assert_project(
    project: dict[str, Any],
    ids: dict[str, str],
    *,
    revision: int,
    drums_gain: float,
    synth_muted: bool,
) -> None:
    _require(project["revision"]["number"] == revision, "Unexpected project revision")
    transport = project["transport"]
    _require(transport["tempo_bpm"] == 120.0, "Fixture tempo must be 120 BPM")
    _require(transport["quantization"] == "bar", "Fixture quantization must be one bar")
    _require(transport["sample_rate"] == 44_100, "Fixture sample rate must be 44.1 kHz")
    _require(len(project["tracks"]) == 2, "Fixture must contain two tracks")
    _require(len(project["scenes"]) == 2, "Fixture must contain two scenes")
    _require(len(project["assets"]) == 2, "Fixture must contain two assets")
    _require(len(project["clips"]) == 4, "Fixture must contain four clips")
    _require(len(project["clip_slots"]) == 4, "Fixture must populate all four slots")

    tracks = {track["id"]: track for track in project["tracks"]}
    drums = tracks[ids["drums"]]
    synth = tracks[ids["synth"]]
    _require(drums["name"] == "Drums" and drums["order"] == 0, "Drums track mismatch")
    _require(synth["name"] == "Synth" and synth["order"] == 1, "Synth track mismatch")
    _require(drums["mixer"]["gain_db"] == drums_gain, "Drums gain mismatch")
    _require(drums["mixer"]["pan"] == -0.25, "Drums pan mismatch")
    _require(synth["mixer"]["gain_db"] == -9.0, "Synth gain mismatch")
    _require(synth["mixer"]["pan"] == 0.25, "Synth pan mismatch")
    _require(synth["mixer"]["muted"] is synth_muted, "Synth mute mismatch")

    scenes = {scene["id"]: scene for scene in project["scenes"]}
    _require(scenes[ids["verse"]]["name"] == "Verse", "Verse scene mismatch")
    _require(scenes[ids["chorus"]]["name"] == "Chorus", "Chorus scene mismatch")
    _require(
        {clip["id"] for clip in project["clips"]}
        == {
            ids["kick-clip"],
            ids["tone-clip"],
            ids["chorus-kick-clip"],
            ids["chorus-tone-clip"],
        },
        "Fixture clip IDs mismatch",
    )
    _require(
        {slot["id"] for slot in project["clip_slots"]}
        == {
            ids["kick-slot"],
            ids["tone-slot"],
            ids["chorus-kick-slot"],
            ids["chorus-tone-slot"],
        },
        "Fixture slot IDs mismatch",
    )


def _project_from(envelope: dict[str, Any]) -> dict[str, Any]:
    project = envelope.get("data")
    if not isinstance(project, dict):
        raise RuntimeError(f"Project command did not return project data: {envelope!r}")
    return cast(dict[str, Any], project)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _open_session(page: Page, url: str, timeout_ms: float) -> None:
    page.goto(url)
    expect(page.locator("#boot-screen")).to_be_hidden(timeout=timeout_ms)
    expect(page.get_by_test_id("socket-status")).to_contain_text("Live", timeout=timeout_ms)


def main() -> int:
    args = _parse_args()
    if args.timeout <= 0:
        raise ValueError("--timeout must be positive")
    app_python = args.app_python.expanduser().resolve(strict=True)
    run_directory = _new_run_directory(args.output_dir)
    cli_log = run_directory / "cli.log"
    service_log = run_directory / "service.log"
    trace_path = run_directory / "browser-trace.zip"
    screenshot_path = run_directory / "browser-failure.png"
    project_path = run_directory / "phase8-poc.vibesound-work"

    _run_cli(
        app_python,
        run_directory,
        cli_log,
        "demo",
        project_path,
        "--no-serve",
        timeout=args.timeout,
    )

    report: dict[str, Any] = {
        "status": "running",
        "app_python": str(app_python),
        "project_path": str(project_path),
        "steps": [],
    }
    try:
        with _running_service(
            app_python,
            project_path,
            run_directory,
            service_log,
            args.timeout,
        ) as url:
            initial = _project_from(
                _run_cli(
                    app_python,
                    run_directory,
                    cli_log,
                    "project",
                    "show",
                    project_path,
                    "--url",
                    url,
                    timeout=args.timeout,
                )
            )
            ids = _demo_ids(initial["project_id"])
            _assert_project(initial, ids, revision=1, drums_gain=-3.0, synth_muted=True)
            report["steps"].append("fixture_initialized")

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=not args.headed)
                context = browser.new_context()
                context.tracing.start(screenshots=True, snapshots=True, sources=True)
                page = context.new_page()
                try:
                    timeout_ms = args.timeout * 1000.0
                    _open_session(page, url, timeout_ms)
                    drums_verse = page.get_by_test_id(
                        f"slot-{ids['drums']}-{ids['verse']}"
                    )
                    synth_verse = page.get_by_test_id(
                        f"slot-{ids['synth']}-{ids['verse']}"
                    )
                    drums_verse.click()
                    synth_verse.click()
                    expect(drums_verse).to_have_attribute(
                        "data-state", "active", timeout=timeout_ms
                    )
                    expect(synth_verse).to_have_attribute(
                        "data-state", "active", timeout=timeout_ms
                    )
                    report["steps"].append("browser_clips_launched")

                    _run_cli(
                        app_python,
                        run_directory,
                        cli_log,
                        "session",
                        "launch",
                        project_path,
                        "--track",
                        "Drums",
                        "--scene",
                        "Chorus",
                        "--url",
                        url,
                        timeout=args.timeout,
                    )
                    drums_chorus = page.get_by_test_id(
                        f"slot-{ids['drums']}-{ids['chorus']}"
                    )
                    expect(drums_chorus).to_have_attribute(
                        "data-state", "active", timeout=timeout_ms
                    )
                    expect(drums_verse).to_have_attribute(
                        "data-state", "idle", timeout=timeout_ms
                    )
                    report["steps"].append("cli_clip_reconciled")

                    valid_operations = run_directory / "valid-transaction.json"
                    valid_operations.write_text(
                        json.dumps(
                            [
                                {
                                    "op": "mixer.update",
                                    "track_id": ids["drums"],
                                    "gain_db": -6.0,
                                },
                                {
                                    "op": "mixer.update",
                                    "track_id": ids["synth"],
                                    "muted": False,
                                },
                            ],
                            indent=2,
                        ),
                        encoding="utf-8",
                    )
                    committed = _run_cli(
                        app_python,
                        run_directory,
                        cli_log,
                        "transaction",
                        "commit",
                        project_path,
                        valid_operations,
                        "--url",
                        url,
                        timeout=args.timeout,
                    )
                    _require(
                        committed["data"]["after_revision"] == 2,
                        "Commit must reach revision 2",
                    )
                    expect(page.get_by_test_id("revision")).to_have_text(
                        "REV 2", timeout=timeout_ms
                    )
                    expect(page.get_by_test_id(f"mixer-{ids['drums']}-gain_db")).to_have_value(
                        "-6", timeout=timeout_ms
                    )
                    expect(page.get_by_test_id(f"mixer-{ids['synth']}-muted")).to_have_attribute(
                        "aria-pressed", "false", timeout=timeout_ms
                    )
                    report["steps"].append("transaction_committed")

                    invalid_operations = run_directory / "invalid-transaction.json"
                    invalid_operations.write_text(
                        json.dumps(
                            [
                                {
                                    "op": "set",
                                    "path": f"/tracks/{ids['drums']}/mixer/gain_db",
                                    "value": 99.0,
                                }
                            ],
                            indent=2,
                        ),
                        encoding="utf-8",
                    )
                    rejected = _run_cli(
                        app_python,
                        run_directory,
                        cli_log,
                        "transaction",
                        "preview",
                        project_path,
                        invalid_operations,
                        "--url",
                        url,
                        timeout=args.timeout,
                        expect_success=False,
                    )
                    _require(not rejected["ok"], "Invalid preview must fail")
                    unchanged = _project_from(
                        _run_cli(
                            app_python,
                            run_directory,
                            cli_log,
                            "project",
                            "show",
                            project_path,
                            "--url",
                            url,
                            timeout=args.timeout,
                        )
                    )
                    _assert_project(
                        unchanged,
                        ids,
                        revision=2,
                        drums_gain=-6.0,
                        synth_muted=False,
                    )
                    report["steps"].append("invalid_preview_rejected")

                    render_commands = run_directory / "render-commands.json"
                    render_commands.write_text(
                        json.dumps(
                            [
                                {
                                    "frame": 0,
                                    "operation": "launch_scene",
                                    "scene_id": ids["chorus"],
                                }
                            ],
                            indent=2,
                        ),
                        encoding="utf-8",
                    )
                    rendered = _run_cli(
                        app_python,
                        run_directory,
                        cli_log,
                        "render",
                        project_path,
                        "--bars",
                        "1",
                        "--commands",
                        render_commands,
                        "--output",
                        "phase8-poc.wav",
                        "--url",
                        url,
                        timeout=max(args.timeout, 60.0),
                    )
                    render_path = project_path / "exports" / "phase8-poc.wav"
                    _require(render_path.is_file(), "Render output was not created")
                    info = sf.info(render_path)
                    render_sha256 = _sha256(render_path)
                    _require(info.samplerate == 44_100, "Render sample rate mismatch")
                    _require(info.channels == 2, "Render must be stereo")
                    _require(info.frames == 88_200, "One-bar render must contain 88,200 frames")
                    _require(
                        rendered["data"]["output_sha256"] == render_sha256,
                        "Render job hash does not match the WAV",
                    )
                    report["render"] = {
                        "path": str(render_path),
                        "sha256": render_sha256,
                        "sample_rate": info.samplerate,
                        "channels": info.channels,
                        "frames": info.frames,
                    }
                    report["steps"].append("wav_rendered")
                except Exception:
                    page.screenshot(path=str(screenshot_path), full_page=True)
                    raise
                finally:
                    context.tracing.stop(path=str(trace_path))
                    context.close()
                    browser.close()

        with _running_service(
            app_python,
            project_path,
            run_directory,
            service_log,
            args.timeout,
        ) as reopened_url:
            reopened = _project_from(
                _run_cli(
                    app_python,
                    run_directory,
                    cli_log,
                    "project",
                    "show",
                    project_path,
                    "--url",
                    reopened_url,
                    timeout=args.timeout,
                )
            )
            ids = _demo_ids(reopened["project_id"])
            _assert_project(
                reopened,
                ids,
                revision=2,
                drums_gain=-6.0,
                synth_muted=False,
            )
            _run_cli(
                app_python,
                run_directory,
                cli_log,
                "project",
                "validate",
                project_path,
                "--url",
                reopened_url,
                timeout=args.timeout,
            )
            report["steps"].append("project_reopened_and_validated")

        report["status"] = "passed"
        report["initial_revision"] = 1
        report["final_revision"] = 2
        report_path = run_directory / "phase8-acceptance.json"
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        print(f"Phase 8 acceptance artifacts: {run_directory}")
        return 0
    except Exception:
        report["status"] = "failed"
        (run_directory / "phase8-acceptance.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        print(f"Phase 8 acceptance artifacts: {run_directory}", file=sys.stderr)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
