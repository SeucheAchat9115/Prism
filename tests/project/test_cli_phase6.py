from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner, Result

from vibesound.api import VibeSoundClient, create_app
from vibesound.application import ApplicationService
from vibesound.audio import FakeAudioBackend
from vibesound.cli import app
from vibesound.command_line import support
from vibesound.project import ProjectRepository

from ._helpers import write_wav


class _TestClientTransport(httpx.BaseTransport):
    def __init__(self, api: Any) -> None:
        self._client = TestClient(api)

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        response = self._client.request(
            request.method,
            str(request.url),
            headers=dict(request.headers),
            content=request.read(),
        )
        return httpx.Response(
            response.status_code,
            headers=response.headers,
            content=response.content,
            request=request,
        )

    def close(self) -> None:
        self._client.close()


def _json(result: Result) -> dict[str, Any]:
    assert result.exit_code == 0, result.stdout
    value = cast(dict[str, Any], json.loads(result.stdout))
    assert value["cli_schema_version"] == 1
    assert value["ok"] is True
    return value


def test_service_backed_phase6_cli_workflow(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    working = tmp_path / "phase6.vibesound-work"
    with ProjectRepository.create(working, "Phase 6", sample_rate=8000):
        pass
    service = ApplicationService(working, backend_factory=FakeAudioBackend)
    api = create_app(service)

    def client_factory(
        base_url: str = "http://testserver",
        *,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> VibeSoundClient:
        del transport
        return VibeSoundClient(
            base_url,
            timeout=timeout,
            transport=_TestClientTransport(api),
        )

    monkeypatch.setattr(support, "VibeSoundClient", client_factory)
    runner = CliRunner()
    common = ["--url", "http://127.0.0.1:8765", "--json"]
    source = tmp_path / "sample.wav"
    write_wav(source, frames=400, sample_rate=8000)
    operations = tmp_path / "operations.json"
    operations.write_text(
        json.dumps(
            [
                {
                    "op": "track.create",
                    "track_id": "11111111-1111-4111-8111-111111111111",
                    "name": "Drums",
                },
                {
                    "op": "scene.create",
                    "scene_id": "22222222-2222-4222-8222-222222222222",
                    "name": "Verse",
                },
            ]
        ),
        encoding="utf-8",
    )

    try:
        status = _json(runner.invoke(app, ["server", "status", str(working), *common]))
        preview = _json(
            runner.invoke(
                app,
                ["transaction", "preview", str(working), str(operations), *common],
            )
        )
        committed = _json(
            runner.invoke(
                app,
                ["transaction", "commit", str(working), str(operations), *common],
            )
        )
        resolved = _json(
            runner.invoke(app, ["entity", "resolve", str(working), "track", "drums", *common])
        )
        imported_preview = _json(
            runner.invoke(
                app,
                ["audio", "import", str(working), str(source), "--dry-run", *common],
            )
        )
        imported = _json(
            runner.invoke(
                app,
                [
                    "asset",
                    "import",
                    str(working),
                    str(source),
                    "--idempotency-key",
                    "phase6-import",
                    *common,
                ],
            )
        )
        import_replay = _json(
            runner.invoke(
                app,
                [
                    "audio",
                    "import",
                    str(working),
                    str(source),
                    "--idempotency-key",
                    "phase6-import",
                    *common,
                ],
            )
        )
        session_operations = tmp_path / "session-operations.json"
        session_operations.write_text(
            json.dumps(
                [
                    {
                        "op": "clip.create",
                        "clip_id": "33333333-3333-4333-8333-333333333333",
                        "name": "Beat",
                        "asset_id": imported["data"]["asset_id"],
                        "loop": True,
                    },
                    {
                        "op": "slot.assign",
                        "track_id": "11111111-1111-4111-8111-111111111111",
                        "scene_id": "22222222-2222-4222-8222-222222222222",
                        "clip_id": "33333333-3333-4333-8333-333333333333",
                    },
                ]
            ),
            encoding="utf-8",
        )
        session_setup = _json(
            runner.invoke(
                app,
                [
                    "transaction",
                    "commit",
                    str(working),
                    str(session_operations),
                    *common,
                ],
            )
        )
        launch_preview = _json(
            runner.invoke(
                app,
                [
                    "session",
                    "launch",
                    str(working),
                    "--track",
                    "drums",
                    "--scene",
                    "verse",
                    "--dry-run",
                    *common,
                ],
            )
        )
        launched = _json(
            runner.invoke(
                app,
                [
                    "session",
                    "launch",
                    str(working),
                    "--track",
                    "drums",
                    "--scene",
                    "verse",
                    *common,
                ],
            )
        )
        stop_preview = _json(
            runner.invoke(
                app,
                ["session", "stop", str(working), "--track", "drums", "--dry-run", *common],
            )
        )
        stopped = _json(
            runner.invoke(
                app,
                ["session", "stop", str(working), "--track", "drums", *common],
            )
        )
        state = _json(runner.invoke(app, ["project", "state", str(working), *common]))
        validation = _json(runner.invoke(app, ["project", "validate", str(working), *common]))
        devices = _json(runner.invoke(app, ["audio", "devices", str(working), *common]))
        restart = _json(
            runner.invoke(app, ["audio", "restart", str(working), "--dry-run", *common])
        )
        transport = _json(
            runner.invoke(app, ["transport", "play", str(working), "--dry-run", *common])
        )
        render_preview = _json(
            runner.invoke(
                app,
                ["render", str(working), "--seconds", "0.01", "--dry-run", *common],
            )
        )
        rendered = _json(
            runner.invoke(
                app,
                ["render", str(working), "--seconds", "0.01", "--output", "cli.wav", *common],
            )
        )
        exported = _json(
            runner.invoke(
                app,
                [
                    "project",
                    "export",
                    str(working),
                    "--output",
                    "cli.vibesound",
                    *common,
                ],
            )
        )
        jobs = _json(runner.invoke(app, ["job", "list", str(working), *common]))
        shown_job = _json(
            runner.invoke(
                app,
                ["job", "show", str(working), rendered["data"]["job_id"], *common],
            )
        )
        cancel_preview = _json(
            runner.invoke(
                app,
                [
                    "job",
                    "cancel",
                    str(working),
                    rendered["data"]["job_id"],
                    "--dry-run",
                    *common,
                ],
            )
        )
        detached_preview = _json(
            runner.invoke(
                app,
                ["project", "detach-source", str(working), "--dry-run", *common],
            )
        )
    finally:
        service.close()

    assert status["data"]["status"] == "ready"
    assert preview["dry_run"] is True and preview["data"]["committed"] is False
    assert committed["data"]["after_revision"] == 1
    assert resolved["data"]["id"] == "11111111-1111-4111-8111-111111111111"
    assert imported_preview["dry_run"] is True
    assert imported_preview["project"]["revision"] == 1
    assert imported["command"] == "asset import"
    assert imported["project"]["revision"] == 2
    assert import_replay["data"]["transaction"]["idempotent_replay"] is True
    assert import_replay["project"]["revision"] == 2
    assert session_setup["project"]["revision"] == 3
    assert launch_preview["data"]["clip_id"] == "33333333-3333-4333-8333-333333333333"
    assert launched["data"]["accepted"] is True
    assert stop_preview["dry_run"] is True
    assert stopped["data"]["accepted"] is True
    assert state["data"]["revision"] == 3
    assert validation["data"]["ok"] is True
    assert isinstance(devices["data"]["devices"], list)
    assert restart["data"]["restarted"] is False
    assert transport["data"]["accepted"] is False
    assert render_preview["data"]["kind"] == "render"
    assert rendered["data"]["state"] == "completed"
    assert exported["data"]["state"] == "completed"
    assert len(jobs["data"]["jobs"]) == 2
    assert shown_job["data"]["job_id"] == rendered["data"]["job_id"]
    assert cancel_preview["dry_run"] is True
    assert detached_preview["data"]["applied"] is False


def test_cli_rejects_remote_urls_and_project_mismatches(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    first = tmp_path / "first.vibesound-work"
    second = tmp_path / "second.vibesound-work"
    with ProjectRepository.create(first, "First"):
        pass
    with ProjectRepository.create(second, "Second"):
        pass
    service = ApplicationService(first, backend_factory=FakeAudioBackend)
    api = create_app(service)

    def client_factory(
        base_url: str = "http://testserver",
        *,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> VibeSoundClient:
        del transport
        return VibeSoundClient(
            base_url,
            timeout=timeout,
            transport=_TestClientTransport(api),
        )

    monkeypatch.setattr(support, "VibeSoundClient", client_factory)
    runner = CliRunner()
    try:
        remote = runner.invoke(
            app,
            ["server", "status", str(first), "--url", "http://example.com", "--json"],
        )
        mismatch = runner.invoke(
            app,
            ["server", "status", str(second), "--url", "http://localhost", "--json"],
        )
    finally:
        service.close()

    remote_json = json.loads(remote.stdout)
    mismatch_json = json.loads(mismatch.stdout)
    assert remote.exit_code == 2
    assert remote_json["errors"][0]["code"] == "non_loopback_service"
    assert mismatch.exit_code == 4
    assert mismatch_json["errors"][0]["code"] == "project_mismatch"
