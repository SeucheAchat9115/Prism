from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from prism.api import create_app
from prism.application import ApplicationService
from prism.plugins import (
    PluginConfigStore,
    PluginManager,
    PluginParameter,
    PluginRegistry,
    PluginWorkerStatus,
)
from prism.project import ProjectRepository
from prism.project.models import Track


class _Worker:
    def __init__(self) -> None:
        self.loaded: set[object] = set()
        self.values = {"gain": 0.5}

    def probe(self, _path: Path) -> list[dict[str, str]]:
        return [
            {
                "plugin_identifier": "com.example.gain",
                "name": "Gain",
                "manufacturer": "Prism Tests",
                "version": "1.0",
            }
        ]

    def status(self) -> PluginWorkerStatus:
        return PluginWorkerStatus(state="ready", pid=1234)

    def restart(self) -> PluginWorkerStatus:
        self.loaded.clear()
        return self.status()

    def load(self, instance_id, path, plugin_identifier, **kwargs):
        del path, plugin_identifier
        self.loaded.add(instance_id)
        self.values.update(kwargs.get("parameters", {}))
        return self.parameters(instance_id)

    def parameters(self, instance_id):
        assert instance_id in self.loaded
        return [
            PluginParameter(id="gain", name="Gain", raw_value=self.values["gain"], value="")
        ]

    def set_parameter(self, instance_id, parameter_id, raw_value):
        assert instance_id in self.loaded
        self.values[parameter_id] = raw_value

    def set_bypass(self, instance_id, bypassed):
        assert instance_id in self.loaded
        del bypassed

    def get_state(self, instance_id, *, max_bytes):
        assert instance_id in self.loaded
        assert max_bytes >= len(b"opaque-api-state")
        return b"opaque-api-state"

    def unload(self, instance_id):
        self.loaded.discard(instance_id)

    def close(self):
        self.loaded.clear()


def test_plugin_api_attaches_controls_and_persists_state(tmp_path: Path) -> None:
    plugin_root = tmp_path / "plugins"
    plugin_root.mkdir()
    binary = plugin_root / "Gain.vst3"
    binary.write_bytes(b"gain-v1")
    store = PluginConfigStore(tmp_path / "config" / "plugins.json")
    store.add_search_path(plugin_root)
    store.trust_plugin(binary)
    registry = PluginRegistry(store.registry_path)
    record = registry.scan(
        store.load(),
        lambda _path: [
            {
                "plugin_identifier": "com.example.gain",
                "name": "Gain",
                "manufacturer": "Prism Tests",
                "version": "1.0",
            }
        ],
    ).plugins[0]
    manager = PluginManager(store, _Worker())  # type: ignore[arg-type]

    working = tmp_path / "api.prism-work"
    with ProjectRepository.create(working, "Plugin API") as repository:
        project = repository.get_project()
        track = Track(name="Track")
        project.tracks = [track]
        project.revision.number = 1
        repository.commit_project(project, history={"kind": "track"})

    service = ApplicationService(working, plugin_manager=manager)
    client = TestClient(create_app(service))
    project_id = service.project_id
    try:
        config = client.get("/api/v1/plugins/config")
        assert config.status_code == 200
        assert config.json()["config"]["search_paths"] == [str(plugin_root.resolve())]
        assert client.post(
            "/api/v1/plugins/search-paths", json={"path": str(plugin_root)}
        ).status_code == 200
        assert client.request(
            "DELETE", "/api/v1/plugins/trust", json={"path": str(binary)}
        ).status_code == 200
        assert client.post(
            "/api/v1/plugins/trust", json={"path": str(binary)}
        ).status_code == 200
        rescanned = client.post("/api/v1/plugins/scan")
        assert rescanned.status_code == 200
        assert rescanned.json()["plugins"][0]["available"] is True
        assert client.get("/api/v1/plugins/worker").json()["state"] == "ready"
        assert client.post("/api/v1/plugins/worker/restart").json()["state"] == "ready"

        listed = client.get("/api/v1/plugins")
        assert listed.status_code == 200
        assert listed.json()["plugins"][0]["registry_id"] == str(record.registry_id)

        attached = client.post(
            f"/api/v1/projects/{project_id}/tracks/{track.id}/plugins/{record.registry_id}",
            json={"base_revision": 1},
        )
        assert attached.status_code == 200
        assert attached.json()["after_revision"] == 2
        effect = service.get_project().tracks[0].effects[0]

        parameters = client.get(
            f"/api/v1/projects/{project_id}/plugins/{effect.id}/parameters"
        )
        assert parameters.status_code == 200
        assert parameters.json()["parameters"][0]["id"] == "gain"

        updated = client.post(
            f"/api/v1/projects/{project_id}/plugins/{effect.id}/parameters/gain",
            json={"base_revision": 2, "raw_value": 0.8},
        )
        assert updated.status_code == 200
        assert service.get_project().tracks[0].effects[0].parameters["gain"] == 0.8

        captured = client.post(
            f"/api/v1/projects/{project_id}/plugins/{effect.id}/state",
            json={"base_revision": 3},
        )
        assert captured.status_code == 200
        current_effect = service.get_project().tracks[0].effects[0]
        assert current_effect.state is not None
        assert service._repository.plugin_state_path(current_effect).read_bytes() == (
            b"opaque-api-state"
        )

        bypassed = client.post(
            f"/api/v1/projects/{project_id}/plugins/{effect.id}/bypass",
            json={"base_revision": 4, "bypassed": True},
        )
        assert bypassed.status_code == 200
        assert service.get_project().tracks[0].effects[0].bypassed

        compatibility = client.get(
            f"/api/v1/projects/{project_id}/plugins/compatibility"
        )
        assert compatibility.json()["plugins"][0]["status"] == "bypassed"

        removed = client.post(
            f"/api/v1/projects/{project_id}/transactions",
            json={
                "base_revision": 5,
                "operations": [{"op": "plugin.remove", "instance_id": str(effect.id)}],
            },
        )
        assert removed.status_code == 200
        assert not service.get_project().tracks[0].effects
        assert not (working / "assets" / "plugin-state" / f"{effect.id}.bin").exists()
        removed_path = client.request(
            "DELETE",
            "/api/v1/plugins/search-paths",
            json={"path": str(plugin_root)},
        )
        assert removed_path.json()["search_paths"] == []
    finally:
        client.close()
        service.close()
