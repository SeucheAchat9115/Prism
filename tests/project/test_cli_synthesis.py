from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner, Result

from prism.api import PrismClient, create_app
from prism.application import ApplicationService
from prism.audio import FakeAudioBackend
from prism.cli import app
from prism.command_line import support
from prism.project import ProjectRepository


class _TestClientTransport(httpx.BaseTransport):
    def __init__(self, api: Any) -> None:
        self.client = TestClient(api)

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        response = self.client.request(
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
        self.client.close()


def _json(result: Result) -> dict[str, Any]:
    assert result.exit_code == 0, result.stdout
    return cast(dict[str, Any], json.loads(result.stdout))


def test_native_synth_cli_lists_previews_and_generates(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    working = tmp_path / "cli-synth.prism-work"
    with ProjectRepository.create(working, "CLI synth", sample_rate=8_000):
        pass
    service = ApplicationService(working, backend_factory=FakeAudioBackend)
    api = create_app(service)

    def client_factory(
        base_url: str = "http://testserver",
        *,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> PrismClient:
        del transport
        return PrismClient(
            base_url,
            timeout=timeout,
            transport=_TestClientTransport(api),
        )

    monkeypatch.setattr(support, "PrismClient", client_factory)
    runner = CliRunner()
    common = ["--url", "http://localhost", "--json"]
    try:
        presets = _json(runner.invoke(app, ["synth", "presets", "--json"]))
        preview = _json(
            runner.invoke(
                app,
                [
                    "synth",
                    "generate",
                    str(working),
                    "--preset",
                    "bass",
                    "--sequence",
                    "C2,-,G1,Bb1",
                    "--name",
                    "cli-bass.wav",
                    "--idempotency-key",
                    "cli-bass-v1",
                    "--dry-run",
                    *common,
                ],
            )
        )
        generated = _json(
            runner.invoke(
                app,
                [
                    "synth",
                    "generate",
                    str(working),
                    "--preset",
                    "bass",
                    "--sequence",
                    "C2,-,G1,Bb1",
                    "--name",
                    "cli-bass.wav",
                    "--waveform",
                    "saw",
                    "--cutoff-hz",
                    "700",
                    "--idempotency-key",
                    "cli-bass-v2",
                    *common,
                ],
            )
        )
        invalid = runner.invoke(
            app,
            [
                "synth",
                "generate",
                str(working),
                "--preset",
                "kick",
                "--waveform",
                "sine",
                *common,
            ],
        )
    finally:
        service.close()

    assert len(presets["data"]["presets"]) == 6
    assert preview["dry_run"] is True
    assert preview["data"]["transaction"]["committed"] is False
    assert generated["data"]["spec"]["waveform"] == "saw"
    assert generated["project"]["revision"] == 1
    assert invalid.exit_code == 2
    assert json.loads(invalid.stdout)["errors"][0]["code"] == "invalid_input"
