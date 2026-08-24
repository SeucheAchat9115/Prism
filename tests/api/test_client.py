from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from prism.api import PrismClient, PrismClientError, PrismEventStream
from prism.application import (
    ClipLaunchRequest,
    ClipStopRequest,
    ExportJobRequest,
    RenderJobRequest,
    TransactionRequest,
    TransportRequest,
)
from prism.application.types import BackgroundJob, TransactionResult
from prism.plugins import (
    PluginConfig,
    PluginRecord,
    PluginRegistryDocument,
    PluginTrustRecord,
    PluginWorkerStatus,
)
from prism.project.models import new_project


def test_typed_client_covers_discovery_authoring_upload_and_jobs(tmp_path: Path) -> None:
    project = new_project("Client")
    job_id = uuid4()
    upload_id = uuid4()
    job_polls = 0

    def job(state: str = "completed") -> dict[str, object]:
        return BackgroundJob(
            job_id=job_id,
            kind="render",
            state=state,
            project_id=project.project_id,
            revision=0,
            progress=1.0 if state == "completed" else 0.5,
            request={"seconds": 1.0},
            output_path="render.wav",
            created_at=1.0,
        ).model_dump(mode="json")

    def snapshot() -> dict[str, object]:
        return {
            "project_id": str(project.project_id),
            "revision": 0,
            "engine": {
                "mode": "stopped",
                "position_frame": 0,
                "active_clip_ids": [],
                "pending_action_frames": [],
            },
            "audio": {
                "state": "stopped",
                "device": None,
                "underrun_count": 0,
                "last_error": None,
            },
        }

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal job_polls
        path = request.url.path
        if path.endswith("/health"):
            return httpx.Response(200, json={"ok": True, "status": "healthy"})
        if path.endswith("/readiness"):
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "status": "ready",
                    "project_id": str(project.project_id),
                    "revision": project.revision.number,
                },
            )
        if path.endswith("/capabilities") or path.endswith("/schemas"):
            return httpx.Response(200, json={"ok": True})
        if path.endswith("/resolve"):
            return httpx.Response(200, json={"id": str(project.project_id)})
        if path.endswith("/uploads"):
            return httpx.Response(201, json={"upload": {"upload_id": str(upload_id)}})
        if "/uploads/" in path and request.method == "DELETE":
            return httpx.Response(200, json={"ok": True, "discarded": True})
        if path.endswith("/transactions") or path.endswith("/transactions/preview"):
            return httpx.Response(
                200,
                json=TransactionResult(
                    ok=True,
                    committed=not path.endswith("preview"),
                    base_revision=0,
                    before_revision=0,
                    after_revision=1,
                    current_revision=1,
                ).model_dump(mode="json"),
                )
        if path.endswith("/session/launch") or path.endswith("/session/stop"):
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "accepted": True,
                    "clip_id": str(project.project_id),
                    "action": {
                        "target_frame": 0,
                        "affected_track_ids": [str(project.project_id)],
                        "changed": True,
                    },
                    "snapshot": snapshot(),
                },
            )
        if path.endswith("/transport"):
            return httpx.Response(200, json={"ok": True, "snapshot": snapshot()})
        if path.endswith("/audio/devices"):
            return httpx.Response(200, json={"devices": []})
        if path.endswith("/audio/restart"):
            return httpx.Response(200, json={"ok": True, "snapshot": snapshot()})
        if path.endswith("/render-jobs/preview"):
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "kind": "render",
                    "project_id": str(project.project_id),
                    "revision": 0,
                    "output_path": "render.wav",
                    "request": {"seconds": 1.0},
                },
            )
        if path.endswith("/export-jobs/preview"):
            return httpx.Response(
                200,
                json={
                    "ok": True,
                    "kind": "export",
                    "project_id": str(project.project_id),
                    "revision": 0,
                    "output_path": "project.prism",
                    "request": {},
                },
            )
        if path.endswith("/external-change/resolve"):
            return httpx.Response(200, json={"ok": True})
        if path.endswith("/render-jobs") or path.endswith("/export-jobs"):
            return httpx.Response(202, json={"job": job()})
        if path.endswith(f"/jobs/{job_id}"):
            if request.method == "DELETE":
                return httpx.Response(200, json={"job": job("cancelled")})
            job_polls += 1
            state = "queued" if job_polls == 1 else "completed"
            return httpx.Response(200, json={"job": job(state)})
        return httpx.Response(200, json={"project": project.model_dump(mode="json")})

    audio = tmp_path / "upload.wav"
    audio.write_bytes(b"RIFF-test")
    transport = httpx.MockTransport(handler)
    with PrismClient("http://testserver", transport=transport) as client:
        assert client.health()["status"] == "healthy"
        assert client.readiness().status == "ready"
        assert client.capabilities()["ok"]
        assert client.schemas()["ok"]
        assert client.get_project(project.project_id).name == "Client"
        assert client.resolve_name(project.project_id, "track", "name") == project.project_id

        transaction = TransactionRequest(
            base_revision=0,
            operations=[{"op": "project.rename", "name": "Renamed"}],
        )
        assert client.preview_transaction(project.project_id, transaction).ok
        assert client.commit_transaction(project.project_id, transaction).committed
        assert client.upload_audio(project.project_id, audio, upload_id=upload_id)[
            "upload_id"
        ] == str(upload_id)
        client.discard_upload(project.project_id, upload_id)
        assert client.transport(
            project.project_id,
            TransportRequest(operation="play"),
        ).engine.mode == "stopped"
        assert client.launch_slot(
            project.project_id,
            ClipLaunchRequest(track_id=project.project_id, scene_id=project.project_id),
        ).accepted
        assert client.stop_track(
            project.project_id,
            ClipStopRequest(track_id=project.project_id),
        ).accepted
        assert client.list_devices() == []
        assert client.restart_audio().audio.state == "stopped"
        assert client.preview_render(
            project.project_id,
            RenderJobRequest(seconds=1.0),
        ).kind == "render"
        assert client.preview_export(
            project.project_id,
            ExportJobRequest(),
        ).kind == "export"
        client.resolve_external_change(project.project_id)

        rendered = client.submit_render(
            project.project_id,
            RenderJobRequest(seconds=1.0),
        )
        exported = client.submit_export(project.project_id, ExportJobRequest())
        assert rendered.job_id == exported.job_id == job_id
        assert client.wait_for_job(project.project_id, job_id).state == "completed"
        assert client.cancel_job(project.project_id, job_id).state == "cancelled"


def test_typed_client_normalizes_error_envelopes_and_invalid_json() -> None:
    responses = iter(
        [
            httpx.Response(
                409,
                json={
                    "ok": False,
                    "errors": [{"code": "conflict", "path": "", "message": "Conflict"}],
                },
            ),
            httpx.Response(500, content=b"not-json"),
            httpx.Response(500, content=json.dumps([]).encode()),
        ]
    )
    client = PrismClient(
        "http://testserver",
        transport=httpx.MockTransport(lambda _request: next(responses)),
    )
    try:
        with pytest.raises(PrismClientError) as conflict:
            client.health()
        assert conflict.value.status_code == 409
        assert conflict.value.issues[0].code == "conflict"
        with pytest.raises(PrismClientError, match="not JSON"):
            client.health()
        with pytest.raises(PrismClientError, match="not an object"):
            client.health()
    finally:
        client.close()


def test_typed_client_covers_machine_plugin_policy_and_worker_control() -> None:
    registry_id = uuid4()
    trust = PluginTrustRecord(
        path="C:/Plugins/Gain.vst3",
        binary_sha256="a" * 64,
        trusted_at=1.0,
    )
    registry = PluginRegistryDocument(
        scanned_at=2.0,
        plugins=[
            PluginRecord(
                registry_id=registry_id,
                path=trust.path,
                plugin_identifier="com.example.gain",
                binary_sha256=trust.binary_sha256,
                name="Gain",
                trusted=True,
                available=True,
            )
        ],
    )

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/config"):
            return httpx.Response(200, json={"config": PluginConfig().model_dump(mode="json")})
        if path.endswith("/search-paths"):
            return httpx.Response(200, json={"search_paths": ["C:/Plugins"]})
        if path.endswith("/trust"):
            if request.method == "DELETE":
                return httpx.Response(200, json={"ok": True})
            return httpx.Response(200, json={"trust": trust.model_dump(mode="json")})
        if path.endswith("/scan") or path.endswith("/plugins"):
            return httpx.Response(200, json=registry.model_dump(mode="json"))
        if path.endswith("/worker/restart") or path.endswith("/worker"):
            return httpx.Response(
                200,
                json=PluginWorkerStatus(state="ready", pid=1234).model_dump(mode="json"),
            )
        raise AssertionError(f"Unexpected plugin request: {request.method} {path}")

    with PrismClient(
        "http://testserver",
        transport=httpx.MockTransport(handler),
    ) as client:
        assert client.plugin_config()["schema_version"] == 1
        assert client.add_plugin_search_path("C:/Plugins") == ["C:/Plugins"]
        assert client.remove_plugin_search_path("C:/Plugins") == ["C:/Plugins"]
        assert client.trust_plugin(trust.path) == trust
        client.revoke_plugin(trust.path)
        assert client.scan_plugins() == registry
        assert client.list_plugins() == registry
        assert client.plugin_worker_status().state == "ready"
        assert client.restart_plugin_worker().pid == 1234


def test_typed_event_stream_is_bounded_and_decodes_json(monkeypatch) -> None:
    project_id = uuid4()
    captured: dict[str, object] = {}

    class Connection:
        def recv(self, timeout=None):
            captured["timeout"] = timeout
            return json.dumps(
                {
                    "type": "transport.changed",
                    "project_id": str(project_id),
                    "revision": 2,
                    "payload": {"operation": "play"},
                }
            )

        def close(self) -> None:
            captured["closed"] = True

    def fake_connect(uri, **kwargs):
        captured["uri"] = uri
        captured.update(kwargs)
        return Connection()

    monkeypatch.setattr("prism.api.client.connect", fake_connect)
    with PrismEventStream("http://127.0.0.1:8765", project_id, timeout=3.0) as stream:
        event = stream.receive(timeout=1.0)

    assert event.type == "transport.changed"
    assert event.payload == {"operation": "play"}
    assert captured["uri"] == f"ws://127.0.0.1:8765/api/v1/projects/{project_id}/events"
    assert captured["max_size"] == 1024 * 1024
    assert captured["max_queue"] == 16
    assert captured["proxy"] is None
    assert captured["timeout"] == 1.0
    assert captured["closed"] is True
