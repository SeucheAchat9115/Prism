"""Redistributable synthetic demo used by installed-package acceptance checks."""

from __future__ import annotations

import io
from pathlib import Path
from uuid import UUID, uuid5

import numpy as np
import soundfile as sf

from vibesound.application import ApplicationService, TransactionRequest
from vibesound.audio import FakeAudioBackend
from vibesound.project import ProjectRepository
from vibesound.project.models import Project


def ensure_demo(path: Path | str) -> Project:
    """Create or reopen a demo exclusively through public service contracts."""

    working_path = Path(path).resolve(strict=False)
    if not working_path.exists():
        with ProjectRepository.create(
            working_path,
            "VibeSound demo",
            tempo_bpm=120.0,
            sample_rate=44_100,
        ):
            pass
    service = ApplicationService(working_path, backend_factory=FakeAudioBackend)
    try:
        project = service.get_project()
        if project.tracks or project.assets:
            return project
        kick_upload = service.stage_audio(_wave_payload(55.0), "synthetic-kick.wav")
        tone_upload = service.stage_audio(_wave_payload(220.0), "synthetic-tone.wav")
        ids = {
            name: uuid5(project.project_id, f"vibesound-demo:{name}")
            for name in (
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
        }
        request = TransactionRequest.model_validate(
            {
                "base_revision": project.revision.number,
                "idempotency_key": "vibesound-installed-demo-v2",
                "operations": [
                    {
                        "op": "track.create",
                        "track_id": ids["drums"],
                        "name": "Drums",
                        "order": 0,
                    },
                    {
                        "op": "track.create",
                        "track_id": ids["synth"],
                        "name": "Synth",
                        "order": 1,
                    },
                    {
                        "op": "scene.create",
                        "scene_id": ids["verse"],
                        "name": "Verse",
                        "order": 0,
                    },
                    {
                        "op": "scene.create",
                        "scene_id": ids["chorus"],
                        "name": "Chorus",
                        "order": 1,
                    },
                    {
                        "op": "asset.import",
                        "upload_id": kick_upload.upload_id,
                        "asset_id": ids["kick-asset"],
                    },
                    {
                        "op": "asset.import",
                        "upload_id": tone_upload.upload_id,
                        "asset_id": ids["tone-asset"],
                    },
                    {
                        "op": "clip.create",
                        "clip_id": ids["kick-clip"],
                        "name": "Synthetic kick",
                        "asset_id": ids["kick-asset"],
                        "loop": True,
                    },
                    {
                        "op": "clip.create",
                        "clip_id": ids["tone-clip"],
                        "name": "Synthetic tone",
                        "asset_id": ids["tone-asset"],
                        "loop": True,
                        "gain_db": -9.0,
                    },
                    {
                        "op": "clip.create",
                        "clip_id": ids["chorus-kick-clip"],
                        "name": "Chorus kick",
                        "asset_id": ids["kick-asset"],
                        "loop": True,
                        "gain_db": -3.0,
                    },
                    {
                        "op": "clip.create",
                        "clip_id": ids["chorus-tone-clip"],
                        "name": "Chorus tone",
                        "asset_id": ids["tone-asset"],
                        "loop": True,
                        "gain_db": -6.0,
                    },
                    {
                        "op": "slot.assign",
                        "slot_id": ids["kick-slot"],
                        "track_id": ids["drums"],
                        "scene_id": ids["verse"],
                        "clip_id": ids["kick-clip"],
                    },
                    {
                        "op": "slot.assign",
                        "slot_id": ids["tone-slot"],
                        "track_id": ids["synth"],
                        "scene_id": ids["verse"],
                        "clip_id": ids["tone-clip"],
                    },
                    {
                        "op": "slot.assign",
                        "slot_id": ids["chorus-kick-slot"],
                        "track_id": ids["drums"],
                        "scene_id": ids["chorus"],
                        "clip_id": ids["chorus-kick-clip"],
                    },
                    {
                        "op": "slot.assign",
                        "slot_id": ids["chorus-tone-slot"],
                        "track_id": ids["synth"],
                        "scene_id": ids["chorus"],
                        "clip_id": ids["chorus-tone-clip"],
                    },
                    {
                        "op": "mixer.update",
                        "track_id": ids["drums"],
                        "gain_db": -3.0,
                        "pan": -0.25,
                    },
                    {
                        "op": "mixer.update",
                        "track_id": ids["synth"],
                        "gain_db": -9.0,
                        "pan": 0.25,
                        "muted": True,
                    },
                ],
            }
        )
        result = service.commit_transaction(request)
        if not result.ok:
            details = "; ".join(issue.message for issue in result.errors)
            raise RuntimeError(f"Could not create the demo project: {details}")
        return service.get_project()
    finally:
        service.close()


def _wave_payload(frequency: float, *, sample_rate: int = 44_100) -> io.BytesIO:
    frames = sample_rate // 2
    time = np.arange(frames, dtype=np.float64) / sample_rate
    envelope = np.exp(-5.0 * time)
    samples = (0.35 * np.sin(2.0 * np.pi * frequency * time) * envelope).astype(np.float32)
    output = io.BytesIO()
    sf.write(output, samples, sample_rate, format="WAV", subtype="FLOAT")
    output.seek(0)
    return output


def demo_ids(project_id: UUID) -> dict[str, UUID]:
    """Return stable fixture IDs for installed acceptance tests."""

    return {
        name: uuid5(project_id, f"vibesound-demo:{name}")
        for name in (
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
    }
