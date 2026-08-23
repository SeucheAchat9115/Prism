from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient
from project._helpers import write_wav

from prism.api import PrismClient, create_app
from prism.application import (
    ApplicationService,
    ExportJobRequest,
    RenderJobRequest,
    TransactionRequest,
)
from prism.audio import FakeAudioBackend
from prism.demo import ensure_demo
from prism.project import load_project


class _TestClientTransport(httpx.BaseTransport):
    def __init__(self, app) -> None:
        self._client = TestClient(app)

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


def test_public_contract_can_author_render_export_and_reopen(tmp_path: Path) -> None:
    working = tmp_path / "acceptance.prism-work"
    initial = ensure_demo(working)
    service = ApplicationService(working, backend_factory=FakeAudioBackend)
    transport = _TestClientTransport(create_app(service))
    client = PrismClient("http://testserver", transport=transport)
    source = tmp_path / "agent.wav"
    write_wav(source, frames=400, sample_rate=8000)
    track_id, scene_id, asset_id, clip_id = [uuid4() for _ in range(4)]
    try:
        assert client.health()["ok"]
        assert client.capabilities()["jobs"]["render"]
        project = client.get_project(initial.project_id)
        upload = client.upload_audio(project.project_id, source)
        transaction = TransactionRequest.model_validate(
            {
                "base_revision": project.revision.number,
                "idempotency_key": "acceptance-authoring-v1",
                "operations": [
                    {"op": "track.create", "track_id": track_id, "name": "Agent track"},
                    {"op": "scene.create", "scene_id": scene_id, "name": "Agent scene"},
                    {
                        "op": "asset.import",
                        "upload_id": upload["upload_id"],
                        "asset_id": asset_id,
                    },
                    {
                        "op": "clip.create",
                        "clip_id": clip_id,
                        "name": "Agent clip",
                        "asset_id": asset_id,
                        "loop": True,
                    },
                    {
                        "op": "slot.assign",
                        "track_id": track_id,
                        "scene_id": scene_id,
                        "clip_id": clip_id,
                    },
                ],
            }
        )
        preview = client.preview_transaction(project.project_id, transaction)
        committed = client.commit_transaction(project.project_id, transaction)
        mixer = client.commit_transaction(
            project.project_id,
            TransactionRequest.model_validate(
                {
                    "base_revision": committed.after_revision,
                    "idempotency_key": "acceptance-mixer-v1",
                    "operations": [
                        {"op": "mixer.update", "track_id": track_id, "gain_db": -4.0}
                    ],
                }
            ),
        )

        assert preview.ok and not preview.committed
        assert committed.created_ids.clips == [clip_id]
        assert mixer.ok, mixer.model_dump(mode="json")
        assert mixer.runtime_impact == "incremental_refresh"
        render = client.submit_render(
            project.project_id,
            RenderJobRequest(
                output_path="acceptance.wav",
                seconds=0.1,
                commands=[
                    {
                        "frame": 0,
                        "operation": "launch_scene",
                        "scene_id": scene_id,
                    }
                ],
            ),
        )
        rendered = client.wait_for_job(project.project_id, render.job_id)
        exported = client.wait_for_job(
            project.project_id,
            client.submit_export(
                project.project_id,
                ExportJobRequest(output_path="acceptance.prism"),
            ).job_id,
        )

        assert rendered.state == "completed" and rendered.output_sha256
        assert exported.state == "completed" and exported.output_sha256
        portable = Path(exported.output_path or "")
    finally:
        client.close()
        service.close()

    reopened = load_project(portable)
    assert reopened.project_id == initial.project_id
    assert reopened.revision.number == mixer.after_revision
    assert {item.id for item in reopened.assets}.issuperset({asset_id})
    assert {item.id for item in reopened.clips}.issuperset({clip_id})
