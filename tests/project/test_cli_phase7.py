from __future__ import annotations

import importlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from prism.cli import app
from prism.demo import ensure_demo

command_line_app = importlib.import_module("prism.command_line.app")


def _json_lines(output: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in output.splitlines() if line.strip()]


def _stub_server(monkeypatch, *, host: str = "127.0.0.1", port: int = 43117) -> None:
    def run_server(
        _path: Path,
        *,
        host: str,
        port: int,
        started: Callable[[str, int], object],
        **_kwargs: object,
    ) -> None:
        del host, port
        started(host_value, port_value)

    host_value = host
    port_value = port
    monkeypatch.setattr(command_line_app, "run_server", run_server)


def test_serve_open_waits_for_bound_url_and_reports_json(monkeypatch, tmp_path: Path) -> None:
    working = tmp_path / "browser-open.prism-work"
    ensure_demo(working)
    _stub_server(monkeypatch, port=43118)
    opened: list[tuple[str, int]] = []
    monkeypatch.setattr(
        command_line_app.webbrowser,
        "open",
        lambda url, new: opened.append((url, new)) or True,
    )

    result = CliRunner().invoke(app, ["serve", str(working), "--open", "--json"])

    assert result.exit_code == 0, result.stdout
    lifecycle = _json_lines(result.stdout)[0]
    assert opened == [("http://127.0.0.1:43118", 2)]
    assert lifecycle["data"] == {
        "status": "starting",
        "url": "http://127.0.0.1:43118",
        "open_requested": True,
        "browser_opened": True,
    }
    assert lifecycle["warnings"] == []


def test_serve_open_failure_is_nonfatal_and_dry_run_never_opens(
    monkeypatch,
    tmp_path: Path,
) -> None:
    working = tmp_path / "browser-failure.prism-work"
    ensure_demo(working)
    _stub_server(monkeypatch)
    calls = 0

    def reject_open(_url: str, *, new: int) -> bool:
        nonlocal calls
        del new
        calls += 1
        return False

    monkeypatch.setattr(command_line_app.webbrowser, "open", reject_open)
    served = CliRunner().invoke(app, ["serve", str(working), "--open", "--json"])
    dry_run = CliRunner().invoke(
        app,
        ["serve", str(working), "--open", "--dry-run", "--json"],
    )

    assert served.exit_code == 0, served.stdout
    lifecycle = _json_lines(served.stdout)[0]
    assert lifecycle["data"]["browser_opened"] is False
    assert lifecycle["warnings"][0]["code"] == "browser_open_failed"
    assert dry_run.exit_code == 0, dry_run.stdout
    assert json.loads(dry_run.stdout)["data"]["open_requested"] is True
    assert json.loads(dry_run.stdout)["data"]["browser_opened"] is False
    assert calls == 1


def test_demo_rejects_open_without_server(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        app,
        ["demo", str(tmp_path / "no-server.prism-work"), "--no-serve", "--open", "--json"],
    )

    assert result.exit_code == 2
    assert json.loads(result.stdout)["errors"][0]["code"] == "open_requires_server"
