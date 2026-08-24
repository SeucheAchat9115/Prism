from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner, Result

from prism.api import PrismClient, create_app
from prism.application import ApplicationService
from prism.cli import app
from prism.command_line import support
from prism.plugins import (
    PluginConfigStore,
    PluginManager,
    PluginParameter,
    PluginRegistry,
    PluginWorkerStatus,
)
from prism.project import ProjectRepository
from prism.project.models import Track

command_line_app = importlib.import_module("prism.command_line.app")


class _Worker:
    def __init__(self) -> None:
        self.loaded: set[object] = set()
        self.values = {"gain": 0.5}

    def probe(self, _path: Path) -> list[dict[str, str]]:
        return [
            {
                "plugin_identifier": "com.example.cli-gain",
                "name": "CLI Gain",
                "manufacturer": "Prism Tests",
                "version": "1.0",
            }
        ]

    def status(self) -> PluginWorkerStatus:
        return PluginWorkerStatus(state="ready", pid=4321)

    def restart(self) -> PluginWorkerStatus:
        self.loaded.clear()
        return self.status()

    def load(self, instance_id, _path, _plugin_identifier, **kwargs):
        self.loaded.add(instance_id)
        self.values.update(kwargs.get("parameters", {}))
        return self.parameters(instance_id)

    def parameters(self, instance_id):
        assert instance_id in self.loaded
        return [PluginParameter(id="gain", name="Gain", raw_value=self.values["gain"])]

    def set_parameter(self, instance_id, parameter_id, raw_value):
        assert instance_id in self.loaded
        self.values[parameter_id] = raw_value

    def set_bypass(self, instance_id, _bypassed):
        assert instance_id in self.loaded

    def get_state(self, instance_id, *, max_bytes):
        assert instance_id in self.loaded
        assert max_bytes >= len(b"cli-state")
        return b"cli-state"

    def unload(self, instance_id):
        self.loaded.discard(instance_id)

    def close(self):
        self.loaded.clear()


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


def test_phase9_cli_machine_policy_and_project_effect_workflow(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    plugin_root = tmp_path / "plugins"
    plugin_root.mkdir()
    binary = plugin_root / "Gain.vst3"
    binary.write_bytes(b"cli-gain")
    store = PluginConfigStore(tmp_path / "machine" / "plugins.json")

    def manager_factory() -> PluginManager:
        return PluginManager(store, _Worker())  # type: ignore[arg-type]

    monkeypatch.setattr(command_line_app, "PluginManager", manager_factory)
    runner = CliRunner()
    assert _json(
        runner.invoke(app, ["plugin", "path-add", str(plugin_root), "--json"])
    )["data"]["search_paths"] == [str(plugin_root.resolve())]
    trusted = _json(runner.invoke(app, ["plugin", "trust", str(binary), "--json"]))
    assert trusted["data"]["binary_sha256"]
    scanned = _json(runner.invoke(app, ["plugin", "scan", "--json"]))
    record = scanned["data"]["plugins"][0]
    assert record["available"] is True
    assert _json(runner.invoke(app, ["plugin", "list", "--json"]))["data"] == scanned[
        "data"
    ]

    working = tmp_path / "phase9.prism-work"
    with ProjectRepository.create(working, "Phase 9") as repository:
        project = repository.get_project()
        track = Track(name="Effects")
        project.tracks = [track]
        project.revision.number = 1
        repository.commit_project(project, history={"kind": "track"})

    service_manager = PluginManager(store, _Worker())  # type: ignore[arg-type]
    service = ApplicationService(working, plugin_manager=service_manager)
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
    common = ["--url", "http://localhost", "--json"]
    try:
        empty = _json(
            runner.invoke(app, ["plugin", "compatibility", str(working), *common])
        )
        assert empty["data"]["plugins"] == []

        preview = _json(
            runner.invoke(
                app,
                [
                    "plugin",
                    "attach",
                    str(working),
                    "--track",
                    "Effects",
                    "--registry-id",
                    record["registry_id"],
                    "--dry-run",
                    *common,
                ],
            )
        )
        assert preview["dry_run"] is True
        attached = _json(
            runner.invoke(
                app,
                [
                    "plugin",
                    "attach",
                    str(working),
                    "--track",
                    "Effects",
                    "--registry-id",
                    record["registry_id"],
                    *common,
                ],
            )
        )
        assert attached["project"]["revision"] == 2
        effect = service.get_project().tracks[0].effects[0]

        parameters = _json(
            runner.invoke(
                app,
                ["plugin", "parameters", str(working), str(effect.id), *common],
            )
        )
        assert parameters["data"]["parameters"][0]["id"] == "gain"
        updated = _json(
            runner.invoke(
                app,
                [
                    "plugin",
                    "set",
                    str(working),
                    str(effect.id),
                    "gain",
                    "0.8",
                    *common,
                ],
            )
        )
        assert updated["project"]["revision"] == 3
        bypassed = _json(
            runner.invoke(
                app,
                ["plugin", "bypass", str(working), str(effect.id), *common],
            )
        )
        assert bypassed["project"]["revision"] == 4
        state = _json(
            runner.invoke(
                app,
                ["plugin", "state-save", str(working), str(effect.id), *common],
            )
        )
        assert state["project"]["revision"] == 5
        assert _json(
            runner.invoke(app, ["plugin", "worker-status", str(working), *common])
        )["data"]["state"] == "ready"
        assert _json(
            runner.invoke(app, ["plugin", "worker-restart", str(working), *common])
        )["data"]["state"] == "ready"
        compatibility = _json(
            runner.invoke(app, ["plugin", "compatibility", str(working), *common])
        )
        assert compatibility["data"]["plugins"][0]["status"] == "bypassed"

        removal = _json(
            runner.invoke(
                app,
                ["plugin", "remove", str(working), str(effect.id), *common],
            )
        )
        assert removal["project"]["revision"] == 6
        assert not service.get_project().tracks[0].effects
    finally:
        service.close()

    _json(runner.invoke(app, ["plugin", "revoke", str(binary), "--json"]))
    removed = _json(
        runner.invoke(app, ["plugin", "path-remove", str(plugin_root), "--json"])
    )
    assert removed["data"]["search_paths"] == []
    assert PluginRegistry(store.registry_path).load().plugins
