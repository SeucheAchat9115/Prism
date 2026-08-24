from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from prism.project.archive import (
    MANIFEST_MEMBER,
    create_project,
    import_audio,
    load_project,
    migrate_project,
    save_project,
    validate_project,
)
from prism.project.errors import InvalidArchiveError
from prism.project.migrations import MigrationRegistry

from ._helpers import write_wav


def _write_manifest(path: Path, document: dict, *members: tuple[str, bytes]) -> None:
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr(MANIFEST_MEMBER, json.dumps(document).encode("utf-8"))
        for name, payload in members:
            archive.writestr(name, payload)


def test_create_load_and_save_are_deterministic(tmp_path: Path) -> None:
    path = tmp_path / "demo.prism"
    created = create_project(path, "Demo")
    first_bytes = path.read_bytes()

    loaded = load_project(path)
    save_project(path, loaded)

    assert loaded == created
    assert path.read_bytes() == first_bytes


def test_import_audio_copies_asset_and_updates_revision(tmp_path: Path) -> None:
    project_path = tmp_path / "demo.prism"
    source_path = tmp_path / "Drums With Spaces.wav"
    original_bytes = write_wav(source_path)
    create_project(project_path, "Demo")

    asset = import_audio(project_path, source_path)
    loaded = load_project(project_path)
    report = validate_project(project_path)

    assert report.ok
    assert loaded.revision.number == 1
    assert loaded.assets[0] == asset
    with ZipFile(project_path) as archive:
        assert archive.read(asset.member_path) == original_bytes
    assert source_path.read_bytes() == original_bytes


def test_validate_detects_corrupted_asset_bytes(tmp_path: Path) -> None:
    project_path = tmp_path / "demo.prism"
    source_path = tmp_path / "tone.wav"
    write_wav(source_path)
    create_project(project_path, "Demo")
    asset = import_audio(project_path, source_path)

    with ZipFile(project_path, "r") as source_archive:
        manifest = source_archive.read(MANIFEST_MEMBER)
        corrupted = bytearray(source_archive.read(asset.member_path))
        corrupted[-1] ^= 0xFF
    with ZipFile(project_path, "w", compression=ZIP_DEFLATED) as destination:
        destination.writestr(MANIFEST_MEMBER, manifest)
        destination.writestr(asset.member_path, bytes(corrupted))

    report = validate_project(project_path)

    assert not report.ok
    assert any(issue.code == "asset_hash_mismatch" for issue in report.issues)


def test_unsafe_archive_member_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "unsafe.prism"
    _write_manifest(path, {"schema_version": 1}, ("../outside.wav", b"bad"))

    with pytest.raises(InvalidArchiveError, match="Unsafe archive member"):
        load_project(path)


def test_missing_asset_member_is_reported(tmp_path: Path) -> None:
    project_path = tmp_path / "demo.prism"
    source_path = tmp_path / "tone.wav"
    write_wav(source_path)
    create_project(project_path, "Demo")
    asset = import_audio(project_path, source_path)

    with ZipFile(project_path, "r") as source_archive:
        document = json.loads(source_archive.read(MANIFEST_MEMBER))
    with ZipFile(project_path, "w", compression=ZIP_DEFLATED) as destination:
        destination.writestr(MANIFEST_MEMBER, json.dumps(document).encode("utf-8"))

    report = validate_project(project_path)

    assert not report.ok
    assert report.issues[0].code == "missing_asset_member"
    assert asset.member_path in report.issues[0].message


def test_failed_save_preserves_original_archive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_path = tmp_path / "demo.prism"
    create_project(project_path, "Demo")
    original_bytes = project_path.read_bytes()
    project = load_project(project_path)
    project.name = "Changed"

    def fail_replace(_source: str | bytes | Path, _destination: str | bytes | Path) -> None:
        raise OSError("simulated replacement failure")

    monkeypatch.setattr("prism.project.archive.os.replace", fail_replace)
    with pytest.raises(OSError, match="simulated replacement failure"):
        save_project(project_path, project)

    assert project_path.read_bytes() == original_bytes
    assert not list(tmp_path.glob(".demo.prism.*.tmp"))


def test_registered_migration_is_in_memory_until_explicit_save(tmp_path: Path) -> None:
    project_path = tmp_path / "legacy.prism"
    document = {
        "schema_version": 0,
        "project_id": "00000000-0000-0000-0000-000000000001",
        "name": "Legacy",
        "revision": {"number": 0},
        "transport": {
            "tempo_bpm": 120,
            "sample_rate": 44100,
            "time_signature_numerator": 4,
            "time_signature_denominator": 4,
            "quantization": "bar",
        },
        "tracks": [],
        "scenes": [],
        "clips": [],
        "clip_slots": [],
        "assets": [],
    }
    _write_manifest(project_path, document)
    before = project_path.read_bytes()
    registry = MigrationRegistry()
    registry.register(0, 1, lambda value: value)
    registry.register(1, 2, lambda value: value)

    assert load_project(project_path, registry=registry).schema_version == 2
    assert project_path.read_bytes() == before

    migrate_project(project_path, registry=registry)

    assert load_project(project_path).schema_version == 2
    assert project_path.read_bytes() != before
