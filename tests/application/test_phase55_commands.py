from __future__ import annotations

import io
from pathlib import Path
from uuid import uuid4

import pytest
from project._helpers import write_wav

from prism.application import (
    ApplicationError,
    ApplicationService,
    TransactionRequest,
    TransportRequest,
)
from prism.audio import FakeAudioBackend
from prism.project import create_project

from ._helpers import make_archive_fixture


def _empty_service(tmp_path: Path) -> tuple[ApplicationService, object]:
    archive = tmp_path / "authoring.prism"
    project = create_project(archive, "Authoring", sample_rate=8000)
    return ApplicationService(archive, backend_factory=FakeAudioBackend), project


def test_public_transaction_builds_complete_project_and_replays_idempotently(
    tmp_path: Path,
) -> None:
    service, project = _empty_service(tmp_path)
    source = tmp_path / "source.wav"
    upload = service.stage_audio(io.BytesIO(write_wav(source)), source.name)
    track_id, scene_id, asset_id, clip_id, slot_id = [uuid4() for _ in range(5)]
    request = TransactionRequest(
        base_revision=project.revision.number,
        idempotency_key="build-demo-1",
        operations=[
            {"op": "track.create", "track_id": track_id, "name": "Drums"},
            {"op": "scene.create", "scene_id": scene_id, "name": "Verse"},
            {"op": "asset.import", "upload_id": upload.upload_id, "asset_id": asset_id},
            {
                "op": "clip.create",
                "clip_id": clip_id,
                "name": "Beat",
                "asset_id": asset_id,
            },
            {
                "op": "slot.assign",
                "slot_id": slot_id,
                "track_id": track_id,
                "scene_id": scene_id,
                "clip_id": clip_id,
            },
        ],
    )
    try:
        preview = service.preview_transaction(request)
        committed = service.commit_transaction(request)
        replay = service.commit_transaction(request.model_copy(update={"base_revision": 1}))
        conflicting_reuse = service.commit_transaction(
            TransactionRequest(
                base_revision=1,
                idempotency_key="build-demo-1",
                operations=[{"op": "project.rename", "name": "Different request"}],
            )
        )

        assert preview.ok and not preview.committed
        assert preview.created_ids.tracks == [track_id]
        assert committed.ok and committed.committed
        assert committed.runtime_impact == "transport_preserving_rebuild"
        assert replay.ok and replay.idempotent_replay
        assert not conflicting_reuse.ok
        assert conflicting_reuse.errors[0].code == "idempotency_conflict"
        assert service.get_project().revision.number == 1
        assert service.resolve_name("track", "drums") == track_id
    finally:
        service.close()


def test_cascade_and_runtime_reset_must_be_explicit(tmp_path: Path) -> None:
    service, project = _empty_service(tmp_path)
    track_id, scene_id = uuid4(), uuid4()
    try:
        created = service.commit_transaction(
            TransactionRequest(
                base_revision=project.revision.number,
                operations=[
                    {"op": "track.create", "track_id": track_id, "name": "Track"},
                    {"op": "scene.create", "scene_id": scene_id, "name": "Scene"},
                ],
            )
        )
        assert created.ok

        reset = TransactionRequest(
            base_revision=created.after_revision,
            operations=[{"op": "transport.update", "sample_rate": 16000}],
        )
        preview = service.preview_transaction(reset)
        rejected = service.commit_transaction(reset)
        accepted = service.commit_transaction(
            reset.model_copy(update={"allow_runtime_reset": True})
        )

        assert preview.ok and preview.runtime_reset_required
        assert not rejected.ok
        assert rejected.errors[0].code == "runtime_reset_required"
        assert accepted.ok and accepted.runtime_reset_performed
    finally:
        service.close()


def test_mixer_update_preserves_running_transport(tmp_path: Path) -> None:
    service, project = _empty_service(tmp_path)
    track_id = uuid4()
    try:
        created = service.commit_transaction(
            TransactionRequest(
                base_revision=project.revision.number,
                operations=[{"op": "track.create", "track_id": track_id, "name": "Track"}],
            )
        )
        service.transport(TransportRequest(operation="play"))
        mixed = service.commit_transaction(
            TransactionRequest(
                base_revision=created.after_revision,
                operations=[{"op": "mixer.update", "track_id": track_id, "gain_db": -6.0}],
            )
        )

        assert mixed.ok
        assert mixed.runtime_impact == "incremental_refresh"
        assert not mixed.runtime_reset_performed
        assert service.get_snapshot().audio.state == "running"
    finally:
        service.close()


def test_all_structural_operations_and_cascades_are_previewable(tmp_path: Path) -> None:
    service, project = _empty_service(tmp_path)
    source = tmp_path / "structure.wav"
    upload = service.stage_audio(io.BytesIO(write_wav(source)), source.name)
    asset_id, clip_id, track_a, track_b, scene_a, scene_b = [uuid4() for _ in range(6)]

    def commit(*operations, allow_runtime_reset: bool = False):
        request = TransactionRequest.model_validate(
            {
                "base_revision": service.get_project().revision.number,
                "allow_runtime_reset": allow_runtime_reset,
                "operations": list(operations),
            }
        )
        result = service.commit_transaction(request)
        assert result.ok, result.errors
        return result

    try:
        commit(
            {"op": "track.create", "track_id": track_a, "name": "A"},
            {"op": "track.create", "track_id": track_b, "name": "B"},
            {"op": "scene.create", "scene_id": scene_a, "name": "One"},
            {"op": "scene.create", "scene_id": scene_b, "name": "Two"},
            {"op": "asset.import", "upload_id": upload.upload_id, "asset_id": asset_id},
            {"op": "clip.create", "clip_id": clip_id, "name": "Clip", "asset_id": asset_id},
            {
                "op": "slot.assign",
                "track_id": track_a,
                "scene_id": scene_a,
                "clip_id": clip_id,
            },
        )
        commit(
            {"op": "project.rename", "name": "Renamed"},
            {"op": "track.rename", "track_id": track_a, "name": "Lead"},
            {"op": "track.reorder", "track_id": track_b, "order": 0},
            {"op": "scene.rename", "scene_id": scene_a, "name": "Intro"},
            {"op": "scene.reorder", "scene_id": scene_b, "order": 0},
            {"op": "transport.update", "tempo_bpm": 100.0, "quantization": "beat"},
            {
                "op": "clip.update",
                "clip_id": clip_id,
                "name": "Edited",
                "duration_frames": 8,
                "gain_db": -3.0,
                "loop": True,
            },
        )
        duplicate_id = uuid4()
        commit(
            {
                "op": "clip.duplicate",
                "clip_id": clip_id,
                "new_clip_id": duplicate_id,
                "name": "Duplicate",
            },
            {
                "op": "slot.assign",
                "track_id": track_b,
                "scene_id": scene_b,
                "clip_id": duplicate_id,
            },
        )
        commit(
            {
                "op": "slot.replace",
                "track_id": track_b,
                "scene_id": scene_b,
                "clip_id": clip_id,
            },
            {"op": "clip.update", "clip_id": clip_id, "clear_duration": True},
        )
        commit({"op": "slot.clear", "track_id": track_b, "scene_id": scene_b})

        blocked_clip = service.preview_transaction(
            TransactionRequest.model_validate(
                {
                    "base_revision": service.get_project().revision.number,
                    "operations": [{"op": "clip.delete", "clip_id": clip_id}],
                }
            )
        )
        assert not blocked_clip.ok
        assert blocked_clip.errors[0].code == "cascade_required"
        assert blocked_clip.cascade_impact[0].dependent_ids.slots

        commit({"op": "clip.delete", "clip_id": clip_id, "cascade": True})
        commit({"op": "clip.delete", "clip_id": duplicate_id})
        commit({"op": "asset.delete", "asset_id": asset_id})
        commit({"op": "track.delete", "track_id": track_a, "cascade": True})
        commit({"op": "scene.delete", "scene_id": scene_a, "cascade": True})

        current = service.get_project()
        assert current.name == "Renamed"
        assert not current.clips and not current.assets
        assert {track.id for track in current.tracks} == {track_b}
        assert {scene.id for scene in current.scenes} == {scene_b}
    finally:
        service.close()


def test_typed_operation_errors_and_ambiguous_names_are_stable(tmp_path: Path) -> None:
    service, project = _empty_service(tmp_path)
    first, second = uuid4(), uuid4()
    try:
        created = service.commit_transaction(
            TransactionRequest.model_validate(
                {
                    "base_revision": project.revision.number,
                    "operations": [
                        {"op": "track.create", "track_id": first, "name": "Same"},
                        {"op": "track.create", "track_id": second, "name": "same"},
                    ],
                }
            )
        )
        assert created.ok
        with pytest.raises(ApplicationError, match="More than one track"):
            service.resolve_name("track", "SAME")

        duplicate_path = service.preview_transaction(
            TransactionRequest(
                base_revision=created.after_revision,
                operations=[
                    {"op": "set", "path": "/name", "value": "one"},
                    {"op": "set", "path": "/name", "value": "two"},
                ],
            )
        )
        occupied = service.preview_transaction(
            TransactionRequest.model_validate(
                {
                    "base_revision": created.after_revision,
                    "operations": [
                        {"op": "track.create", "track_id": first, "name": "Duplicate"}
                    ],
                }
            )
        )
        assert duplicate_path.errors[0].code == "duplicate_path"
        assert occupied.errors[0].code == "duplicate_id"
    finally:
        service.close()


def test_metadata_commit_reuses_prepared_audio_cache(tmp_path: Path) -> None:
    project_path, project, _, _, _ = make_archive_fixture(tmp_path)
    service = ApplicationService(project_path, backend_factory=FakeAudioBackend)
    try:
        cache_files = list(
            (service.working_path / ".prism" / "cache" / "audio").glob("*.npy")
        )
        assert len(cache_files) == 1
        before = cache_files[0].stat().st_mtime_ns
        result = service.commit_transaction(
            TransactionRequest(
                base_revision=project.revision.number,
                operations=[{"op": "project.rename", "name": "Metadata only"}],
            )
        )

        assert result.ok
        assert result.runtime_impact == "none"
        assert cache_files[0].stat().st_mtime_ns == before
    finally:
        service.close()
