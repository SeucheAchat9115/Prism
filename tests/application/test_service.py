from __future__ import annotations

from pathlib import Path
from queue import Empty

from prism.application import (
    ApplicationService,
    ClipLaunchRequest,
    ClipStopRequest,
    TransactionRequest,
    TransportRequest,
)
from prism.audio import FakeAudioBackend

from ._helpers import make_archive_fixture


def _service(path: Path) -> ApplicationService:
    return ApplicationService(path, backend_factory=FakeAudioBackend)


def test_service_preview_is_observational_and_commit_persists(tmp_path: Path) -> None:
    project_path, project, track, _, _ = make_archive_fixture(tmp_path)
    service = _service(project_path)
    subscription = service.subscribe()
    try:
        request = TransactionRequest(
            base_revision=project.revision.number,
            operations=[
                {
                    "op": "set",
                    "path": f"/tracks/{track.id}/mixer/gain_db",
                    "value": -3.0,
                }
            ],
        )
        original_bytes = project_path.read_bytes()

        preview = service.preview_transaction(request)

        assert preview.ok
        assert not preview.committed
        assert preview.current_revision == project.revision.number
        assert project_path.read_bytes() == original_bytes
        assert service.get_project().tracks[0].mixer.gain_db == 0.0
        try:
            subscription.get(timeout=0.01)
        except Empty:
            pass
        else:
            raise AssertionError("Preview must not publish an event")

        committed = service.commit_transaction(request)

        assert committed.ok
        assert committed.committed
        assert committed.before_revision == project.revision.number
        assert committed.after_revision == project.revision.number + 1
        assert committed.changed_paths == [f"/tracks/{track.id}/mixer/gain_db"]
        assert service.get_project().tracks[0].mixer.gain_db == -3.0
        assert service.get_project().revision.number == project.revision.number + 1
        assert "project.changed" == subscription.get(timeout=0.1).type
    finally:
        subscription.close()
        service.close()


def test_service_rejects_stale_and_invalid_transactions_without_partial_changes(
    tmp_path: Path,
) -> None:
    project_path, project, track, _, _ = make_archive_fixture(tmp_path)
    service = _service(project_path)
    try:
        committed = service.commit_transaction(
            TransactionRequest(
                base_revision=project.revision.number,
                operations=[{"op": "set", "path": "/name", "value": "Changed"}],
            )
        )
        assert committed.ok

        stale = service.commit_transaction(
            TransactionRequest(
                base_revision=project.revision.number,
                operations=[{"op": "set", "path": "/name", "value": "Stale"}],
            )
        )
        invalid = service.commit_transaction(
            TransactionRequest(
                base_revision=project.revision.number + 1,
                operations=[
                    {
                        "op": "set",
                        "path": f"/tracks/{track.id}/mixer/gain_db",
                        "value": 99.0,
                    }
                ],
            )
        )

        assert not stale.ok
        assert stale.errors[0].code == "stale_revision"
        assert not invalid.ok
        assert invalid.errors[0].code == "invalid_value"
        assert service.get_project().name == "Changed"
        assert service.get_project().revision.number == project.revision.number + 1
    finally:
        service.close()


def test_service_controls_fake_backend_and_publishes_events(tmp_path: Path) -> None:
    project_path, project, track, scene, clip = make_archive_fixture(tmp_path)
    service = _service(project_path)
    subscription = service.subscribe()
    try:
        service.transport(TransportRequest(operation="play"))
        action = service.launch_clip(
            clip.id,
            ClipLaunchRequest(track_id=track.id, scene_id=scene.id),
        )
        stop = service.stop_clip(clip.id, ClipStopRequest(track_id=track.id))

        assert action.changed
        assert stop.changed
        assert service.get_snapshot().revision == project.revision.number
        assert [subscription.get(timeout=0.1).type for _ in range(3)] == [
            "transport.changed",
            "clip.launched",
            "clip.stopped",
        ]
    finally:
        subscription.close()
        service.close()
