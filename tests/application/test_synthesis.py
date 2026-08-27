from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import numpy as np
import soundfile as sf

from prism.application import (
    ApplicationService,
    RenderJobRequest,
    SynthAssetRequest,
    TransactionRequest,
)
from prism.audio import FakeAudioBackend
from prism.project import ProjectRepository
from prism.synthesis import NativeSynthSpec


def test_native_synth_preview_commit_replay_and_render(tmp_path: Path) -> None:
    working = tmp_path / "synth.prism-work"
    with ProjectRepository.create(
        working,
        "Native synth",
        tempo_bpm=120.0,
        sample_rate=8_000,
    ):
        pass
    service = ApplicationService(working, backend_factory=FakeAudioBackend)
    subscription = service.subscribe()
    asset_id = uuid4()
    request = SynthAssetRequest(
        base_revision=0,
        filename="bass-loop.wav",
        spec=NativeSynthSpec(
            preset="bass",
            sequence=["C2", "-", "G1", "Bb1"],
            bars=1,
        ),
        asset_id=asset_id,
        idempotency_key="native-bass-v1",
    )
    try:
        preview = service.generate_synth_asset(request, preview=True)
        assert preview.ok and preview.preview
        assert not preview.transaction.committed
        assert service.get_project().revision.number == 0
        assert service.get_project().assets == []

        committed = service.generate_synth_asset(request)
        assert committed.ok and committed.transaction.committed
        assert committed.asset_id == asset_id
        assert committed.frames == 16_000
        project = service.get_project()
        assert project.revision.number == 1
        assert project.assets[0].id == asset_id
        audio_path = working / project.assets[0].member_path
        assert audio_path.is_file()
        audio, sample_rate = sf.read(audio_path, always_2d=True, dtype="float32")
        assert sample_rate == 8_000
        assert audio.shape == (16_000, 1)
        assert float(np.max(np.abs(audio))) > 0.01

        assert subscription.get(timeout=1.0).type == "project.changed"
        synth_event = subscription.get(timeout=1.0)
        assert synth_event.type == "synth.asset.generated"
        assert synth_event.payload["asset_id"] == str(asset_id)

        replay = service.generate_synth_asset(request.model_copy(update={"base_revision": 1}))
        assert replay.ok
        assert replay.transaction.idempotent_replay
        assert service.get_project().revision.number == 1

        conflict = service.generate_synth_asset(
            request.model_copy(
                update={
                    "base_revision": 1,
                    "spec": NativeSynthSpec(preset="bass", sequence=["D2"], bars=1),
                }
            )
        )
        assert not conflict.ok
        assert conflict.transaction.errors[0].code == "idempotency_conflict"

        track_id, scene_id, clip_id = uuid4(), uuid4(), uuid4()
        authored = service.commit_transaction(
            TransactionRequest.model_validate(
                {
                    "base_revision": 1,
                    "operations": [
                        {"op": "track.create", "track_id": track_id, "name": "Bass"},
                        {"op": "scene.create", "scene_id": scene_id, "name": "Groove"},
                        {
                            "op": "clip.create",
                            "clip_id": clip_id,
                            "name": "Native bass",
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
        )
        assert authored.ok
        rendered = service.render(
            RenderJobRequest.model_validate(
                {
                "output_path": "native-song.wav",
                "seconds": 1.0,
                "commands": [
                    {"frame": 0, "operation": "launch_scene", "scene_id": scene_id}
                ],
                }
            )
        )
        mix, _ = sf.read(rendered.output_path, always_2d=True, dtype="float32")
        assert float(np.max(np.abs(mix))) > 0.001
    finally:
        subscription.close()
        service.close()
