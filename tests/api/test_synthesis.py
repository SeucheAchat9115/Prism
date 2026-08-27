from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient

from prism.api import PrismClient, create_app
from prism.application import ApplicationService, SynthAssetRequest
from prism.audio import FakeAudioBackend
from prism.project import ProjectRepository
from prism.synthesis import NativeSynthSpec


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


def test_native_synth_api_discovery_preview_commit_and_typed_client(tmp_path: Path) -> None:
    working = tmp_path / "api-synth.prism-work"
    with ProjectRepository.create(working, "API synth", sample_rate=8_000):
        pass
    service = ApplicationService(working, backend_factory=FakeAudioBackend)
    api = create_app(service)
    client = TestClient(api)
    project_id = service.project_id
    asset_id = uuid4()
    payload = {
        "base_revision": 0,
        "filename": "api-lead.wav",
        "asset_id": str(asset_id),
        "idempotency_key": "api-lead-v1",
        "spec": {
            "preset": "lead",
            "sequence": ["C4", "E4", "G4", "-"],
            "bars": 1,
            "waveform": "triangle",
        },
    }
    try:
        capabilities = client.get("/api/v1/capabilities")
        schemas = client.get("/api/v1/schemas")
        presets = client.get("/api/v1/synth/presets")
        preview = client.post(
            f"/api/v1/projects/{project_id}/synth-assets?preview=true",
            json=payload,
        )
        assert capabilities.json()["native_synth"]["asset_generation"] is True
        assert "synth_asset_request" in schemas.json()
        assert len(presets.json()["presets"]) == 6
        assert preview.status_code == 200
        assert preview.json()["preview"] is True
        assert preview.json()["transaction"]["committed"] is False
        assert service.get_project().assets == []

        committed = client.post(
            f"/api/v1/projects/{project_id}/synth-assets",
            json=payload,
        )
        assert committed.status_code == 200
        assert committed.json()["asset_id"] == str(asset_id)
        assert committed.json()["transaction"]["after_revision"] == 1

        invalid = client.post(
            f"/api/v1/projects/{project_id}/synth-assets",
            json={
                **payload,
                "base_revision": 1,
                "idempotency_key": "invalid-kick",
                "spec": {"preset": "kick", "waveform": "sine"},
            },
        )
        assert invalid.status_code == 422
        assert invalid.json()["errors"][0]["code"] == "invalid_request"

        with PrismClient(
            "http://testserver",
            transport=_TestClientTransport(api),
        ) as typed:
            assert typed.synth_presets()[0].name == "kick"
            request = SynthAssetRequest(
                base_revision=1,
                filename="typed-pad.wav",
                spec=NativeSynthSpec(preset="pad", sequence=["C3+E3+G3", "-"]),
                idempotency_key="typed-pad-v1",
            )
            result = typed.generate_synth_asset(project_id, request, preview=True)
            assert result.ok and result.preview
            assert result.spec.preset == "pad"
    finally:
        client.close()
        service.close()
