from __future__ import annotations

import io
import os
from pathlib import Path
from uuid import uuid4
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from prism.project import (
    ExternalProjectChangeError,
    ProjectLockedError,
    ProjectRepository,
    ProjectResourceLimitError,
    RepositoryLimits,
    StagedUploadError,
    WorkingProjectError,
    create_project,
    import_audio,
    load_project,
)

from ._helpers import write_wav


def test_archive_opens_as_sidecar_and_exports_deterministically(tmp_path: Path) -> None:
    archive = tmp_path / "demo.prism"
    audio = tmp_path / "tone.wav"
    write_wav(audio)
    create_project(archive, "Original", sample_rate=8000)
    asset = import_audio(archive, audio)
    portable_bytes = archive.read_bytes()

    with ProjectRepository.open(archive) as repository:
        assert repository.working_path == tmp_path / "demo.prism-work"
        candidate = repository.get_project()
        candidate.name = "Working edit"
        candidate.revision.number += 1
        repository.commit_project(candidate, history={"kind": "test"})

        first, first_hash = repository.export_archive("first.prism")
        second, second_hash = repository.export_archive("second.prism")

        assert first.read_bytes() == second.read_bytes()
        assert first_hash == second_hash
        exported = load_project(first)
        assert exported.name == "Working edit"
        assert exported.assets[0].sha256 == asset.sha256

    assert archive.read_bytes() == portable_bytes


def test_repository_rejects_a_second_writer_lock(tmp_path: Path) -> None:
    archive = tmp_path / "locked.prism"
    create_project(archive, "Locked")

    first = ProjectRepository.open(archive)
    try:
        with pytest.raises(ProjectLockedError):
            ProjectRepository.open(archive)
    finally:
        first.close()


def test_staged_upload_is_streamed_and_does_not_change_revision(tmp_path: Path) -> None:
    archive = tmp_path / "upload.prism"
    source = tmp_path / "source.wav"
    payload = write_wav(source)
    create_project(archive, "Upload", sample_rate=8000)

    with ProjectRepository.open(archive) as repository:
        before = repository.get_project().revision.number
        upload = repository.stage_audio(io.BytesIO(payload), "source.wav")

        assert upload.size_bytes == len(payload)
        assert upload.path.is_file()
        assert repository.get_project().revision.number == before
        assert "path" not in upload.to_public_dict()


def test_requested_upload_id_replays_only_identical_staged_audio(tmp_path: Path) -> None:
    archive = tmp_path / "idempotent-upload.prism"
    source = tmp_path / "source.wav"
    payload = write_wav(source)
    upload_id = uuid4()
    create_project(archive, "Idempotent upload", sample_rate=8000)

    with ProjectRepository.open(archive) as repository:
        first = repository.stage_audio(
            io.BytesIO(payload),
            "source.wav",
            upload_id=upload_id,
        )
        replay = repository.stage_audio(
            io.BytesIO(payload),
            "renamed.wav",
            upload_id=upload_id,
        )

        assert replay == first
        with pytest.raises(StagedUploadError, match="different audio"):
            repository.stage_audio(
                io.BytesIO(payload + b"different"),
                "source.wav",
                upload_id=upload_id,
            )
        assert repository.get_upload(upload_id) == first


def test_external_source_change_pauses_writes_until_detached(tmp_path: Path) -> None:
    archive = tmp_path / "external.prism"
    create_project(archive, "External")

    with ProjectRepository.open(archive) as repository:
        stat = archive.stat()
        os.utime(archive, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
        with pytest.raises(ExternalProjectChangeError):
            repository.check_external_changes()

        repository.detach_source()
        candidate = repository.get_project()
        candidate.name = "Detached"
        candidate.revision.number += 1
        committed = repository.commit_project(candidate, history={"kind": "detached"})

        assert committed.name == "Detached"


def test_archive_member_limit_is_enforced_before_expansion(tmp_path: Path) -> None:
    archive = tmp_path / "oversized.prism"
    with ZipFile(archive, "w", compression=ZIP_DEFLATED) as output:
        output.writestr("project.json", "{}")
        output.writestr("one.bin", b"1")

    with pytest.raises(ProjectResourceLimitError):
        ProjectRepository.open(archive, limits=RepositoryLimits(max_archive_members=1))


def test_layered_validation_and_output_policy_are_explicit(tmp_path: Path) -> None:
    archive = tmp_path / "validation.prism"
    audio = tmp_path / "valid.wav"
    write_wav(audio)
    create_project(archive, "Validation", sample_rate=8000)
    import_audio(archive, audio)

    with ProjectRepository.open(archive) as repository:
        report = repository.validation_report().as_dict()

        assert report["ok"]
        assert set(report["stages"]) == {
            "archive_integrity",
            "schema",
            "project_references",
            "playback_readiness",
            "device_compatibility",
        }
        assert repository.resolve_output("nested/render.wav").is_relative_to(
            repository.exports_path
        )
        with pytest.raises(WorkingProjectError, match="escapes"):
            repository.resolve_output("../outside.wav")


def test_direct_working_project_creation_is_recoverable(tmp_path: Path) -> None:
    working = tmp_path / "direct.prism-work"
    with ProjectRepository.create(working, "Direct") as repository:
        project_id = repository.get_project().project_id
        assert (working / "project.json").is_file()
        assert (working / ".prism" / "repository.json").is_file()

    with ProjectRepository.open(working) as reopened:
        assert reopened.get_project().project_id == project_id
