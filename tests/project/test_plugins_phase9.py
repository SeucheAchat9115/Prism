from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from prism.application.commands import ProjectCommandService
from prism.application.types import TransactionRequest
from prism.project import (
    ProjectRepository,
    WorkingProjectError,
    load_project,
    validate_project,
)
from prism.project.models import PluginInstance, Track, new_project


def _effect() -> PluginInstance:
    return PluginInstance(
        registry_id=uuid4(),
        plugin_identifier="com.example.gain",
        binary_sha256="a" * 64,
        name="Example Gain",
        manufacturer="Prism Tests",
        version="1.0",
    )


def test_schema_one_migrates_track_effect_slots_in_memory(tmp_path: Path) -> None:
    project = new_project("Legacy")
    project.tracks = [Track(name="Track")]
    document = project.model_dump(mode="json")
    document["schema_version"] = 1
    for track in document["tracks"]:
        del track["effects"]
    archive_path = tmp_path / "legacy.prism"
    with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("project.json", json.dumps(document))

    migrated = load_project(archive_path)

    assert migrated.schema_version == 2
    assert migrated.tracks[0].effects == []
    with ZipFile(archive_path) as archive:
        assert json.loads(archive.read("project.json"))["schema_version"] == 1


def test_repository_round_trips_hashed_opaque_plugin_state(tmp_path: Path) -> None:
    working = tmp_path / "state.prism-work"
    with ProjectRepository.create(working, "State") as repository:
        project = repository.get_project()
        effect = _effect()
        project.tracks = [Track(name="Track", effects=[effect])]
        project.revision.number = 1
        repository.commit_project(project, history={"kind": "attach"})

        reference = repository.install_plugin_state(effect.id, b"opaque-state")
        candidate = repository.get_project()
        candidate.tracks[0].effects[0].state = reference.model_copy(
            update={"sha256": "0" * 64}
        )
        candidate.revision.number = 2
        with pytest.raises(WorkingProjectError, match="integrity mismatch"):
            repository.commit_project(candidate, history={"kind": "forged-state"})

        candidate.tracks[0].effects[0].state = reference
        repository.commit_project(candidate, history={"kind": "state"})

        snapshot = repository.snapshot()
        assert snapshot.plugin_state_paths[effect.id].read_bytes() == b"opaque-state"
        snapshot.plugin_state_paths[effect.id].write_bytes(b"tampered")
        with pytest.raises(WorkingProjectError, match="changed during export"):
            repository.export_snapshot(snapshot, "tampered.prism")
        snapshot.plugin_state_paths[effect.id].write_bytes(b"opaque-state")
        exported, _ = repository.export_archive("state.prism")
        assert repository.validation_report().ok

    reopened = load_project(exported)
    assert reopened.tracks[0].effects[0].state == reference
    assert validate_project(exported).ok
    with ZipFile(exported) as archive:
        assert archive.read(reference.member_path) == b"opaque-state"


def test_typed_plugin_operations_and_track_cascade_are_previewable(tmp_path: Path) -> None:
    working = tmp_path / "commands.prism-work"
    with ProjectRepository.create(working, "Commands") as repository:
        commands = ProjectCommandService(repository)
        created, project = commands.commit(
            TransactionRequest(
                base_revision=0,
                operations=[{"op": "track.create", "name": "Track"}],
            )
        )
        assert created.ok and project is not None
        track = project.tracks[0]
        effect = _effect()
        attached, project = commands.commit(
            TransactionRequest(
                base_revision=1,
                operations=[
                    {
                        "op": "plugin.attach",
                        "track_id": track.id,
                        "registry_id": effect.registry_id,
                        "instance_id": effect.id,
                        "plugin_identifier": effect.plugin_identifier,
                        "binary_sha256": effect.binary_sha256,
                        "name": effect.name,
                        "manufacturer": effect.manufacturer,
                        "version": effect.version,
                        "category": effect.category,
                    }
                ],
            )
        )
        assert attached.created_ids.plugin_instances == [effect.id]
        assert project is not None

        updated, project = commands.commit(
            TransactionRequest(
                base_revision=2,
                operations=[
                    {
                        "op": "plugin.parameter.update",
                        "instance_id": effect.id,
                        "parameter_id": "gain",
                        "raw_value": 0.75,
                    },
                    {
                        "op": "plugin.bypass.update",
                        "instance_id": effect.id,
                        "bypassed": True,
                    },
                ],
            )
        )
        assert updated.ok and project is not None
        assert project.tracks[0].effects[0].parameters == {"gain": 0.75}
        assert project.tracks[0].effects[0].bypassed

        preview = commands.preview(
            TransactionRequest(
                base_revision=3,
                operations=[{"op": "track.delete", "track_id": track.id, "cascade": True}],
            )
        )
        assert preview.ok
        assert preview.cascade_impact[0].dependent_ids.plugin_instances == [effect.id]
        assert preview.deleted_ids.plugin_instances == [effect.id]
