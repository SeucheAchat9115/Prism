"""Exercise preview, commit, validation, and stale revision handling."""

from __future__ import annotations

from _support import make_music_fixture, parse_output_dir, print_json

from prism.application import ApplicationService, TransactionRequest
from prism.audio import FakeAudioBackend


def main() -> int:
    run_dir = parse_output_dir(
        "transaction-safety",
        "Demonstrate safe agent transactions on a generated music project.",
    )
    project_path, project, tracks, _, _ = make_music_fixture(run_dir)
    service = ApplicationService(project_path, backend_factory=FakeAudioBackend)
    subscription = service.subscribe()
    try:
        initial_revision = service.get_project().revision.number
        transaction = TransactionRequest.model_validate(
            {
                "base_revision": initial_revision,
                "operations": [
                    {"op": "set", "path": "/name", "value": "Agent Transaction Beat"},
                    {
                        "op": "set",
                        "path": f"/tracks/{tracks['Bass'].id}/mixer/gain_db",
                        "value": -3.0,
                    },
                    {
                        "op": "set",
                        "path": f"/tracks/{tracks['Hats'].id}/mixer/muted",
                        "value": True,
                    },
                ],
            }
        )
        preview = service.preview_transaction(transaction)
        preview_revision = service.get_project().revision.number
        committed = service.commit_transaction(transaction)
        changed_event = subscription.get(timeout=1.0)
        stale = service.commit_transaction(transaction)

        invalid = service.preview_transaction(
            TransactionRequest.model_validate(
                {
                    "base_revision": committed.after_revision,
                    "operations": [
                        {
                            "op": "set",
                            "path": f"/tracks/{tracks['Bass'].id}/mixer/gain_db",
                            "value": 99.0,
                        }
                    ],
                }
            )
        )
        current = service.get_project()
        current_tracks = {track.name: track for track in current.tracks}
        print_json(
            {
                "project_path": str(project_path),
                "project_id": str(project.project_id),
                "initial_revision": initial_revision,
                "preview": {
                    "ok": preview.ok,
                    "committed": preview.committed,
                    "revision_after_preview": preview_revision,
                },
                "commit": {
                    "ok": committed.ok,
                    "after_revision": committed.after_revision,
                    "changed_paths": committed.changed_paths,
                    "event": changed_event.type,
                },
                "stale_commit": {
                    "ok": stale.ok,
                    "error": stale.errors[0].code,
                    "current_revision": stale.current_revision,
                },
                "invalid_preview": {
                    "ok": invalid.ok,
                    "error": invalid.errors[0].code,
                },
                "persisted_state": {
                    "name": current.name,
                    "revision": current.revision.number,
                    "bass_gain_db": current_tracks["Bass"].mixer.gain_db,
                    "hats_muted": current_tracks["Hats"].mixer.muted,
                },
            }
        )
        return 0
    finally:
        subscription.close()
        service.close()


if __name__ == "__main__":
    raise SystemExit(main())
