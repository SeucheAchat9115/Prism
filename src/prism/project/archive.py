"""Atomic ZIP-backed persistence for ``.prism`` projects."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from uuid import uuid4
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile, ZipInfo

import soundfile as sf
from pydantic import ValidationError

from prism.project.errors import (
    AssetImportError,
    InvalidArchiveError,
    InvalidProjectError,
    ProjectArchiveError,
    ProjectValidationError,
    UnsupportedSchemaVersionError,
    ValidationIssue,
)
from prism.project.migrations import DEFAULT_REGISTRY, MigrationRegistry
from prism.project.models import CURRENT_SCHEMA_VERSION, AssetReference, Project, new_project
from prism.project.validation import (
    ValidationReport,
    project_reference_issues,
    pydantic_issues,
)

PROJECT_SUFFIX = ".prism"
MANIFEST_MEMBER = "project.json"
ASSET_PREFIX = "assets/audio/"
PLUGIN_STATE_PREFIX = "assets/plugin-state/"
_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def _project_path(path: Path | str) -> Path:
    project_path = Path(path)
    if project_path.suffix.lower() != PROJECT_SUFFIX:
        raise ProjectArchiveError(f"Project path must end with {PROJECT_SUFFIX}: {project_path}")
    return project_path


def _validate_member_name(name: str) -> None:
    path = PurePosixPath(name)
    if (
        not name
        or "\\" in name
        or path.is_absolute()
        or ".." in path.parts
        or ":" in name
        or name.endswith("/")
    ):
        raise InvalidArchiveError(f"Unsafe archive member path: {name!r}")


def _validate_zip_members(zip_file: ZipFile) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for info in zip_file.infolist():
        _validate_member_name(info.filename)
        if info.filename in seen:
            raise InvalidArchiveError(f"Duplicate archive member: {info.filename}")
        seen.add(info.filename)
        mode = (info.external_attr >> 16) & 0xF000
        if mode == 0xA000:
            raise InvalidArchiveError(f"ZIP symlinks are not allowed: {info.filename}")
        names.append(info.filename)
    if MANIFEST_MEMBER not in seen:
        raise InvalidArchiveError(f"Archive is missing {MANIFEST_MEMBER}")
    return names


def _manifest_bytes(project: Project) -> bytes:
    document = project.model_dump(mode="json")
    return (json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )


def _zip_info(name: str) -> ZipInfo:
    info = ZipInfo(filename=name, date_time=_ZIP_TIMESTAMP)
    info.compress_type = ZIP_DEFLATED
    info.create_system = 0
    info.external_attr = 0
    info.flag_bits |= 0x800
    return info


def _write_archive(
    path: Path,
    project: Project,
    asset_payloads: Mapping[str, bytes],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    os.close(fd)
    temporary_path = Path(temporary_name)
    try:
        with ZipFile(
            temporary_path,
            mode="w",
            compression=ZIP_DEFLATED,
            compresslevel=9,
        ) as archive:
            archive.writestr(_zip_info(MANIFEST_MEMBER), _manifest_bytes(project))
            for member_path in sorted(asset_payloads):
                archive.writestr(_zip_info(member_path), asset_payloads[member_path])
        with temporary_path.open("r+b") as temporary_file:
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def _read_archive_document(
    path: Path | str,
    *,
    registry: MigrationRegistry,
) -> tuple[Project, tuple[str, ...]]:
    project_path = _project_path(path)
    if not project_path.is_file():
        raise InvalidArchiveError(f"Project file does not exist: {project_path}")
    try:
        with ZipFile(project_path, mode="r") as archive:
            member_names = tuple(_validate_zip_members(archive))
            try:
                raw_manifest = archive.read(MANIFEST_MEMBER)
            except KeyError as exc:  # pragma: no cover - guarded by member validation
                raise InvalidArchiveError(f"Archive is missing {MANIFEST_MEMBER}") from exc
    except BadZipFile as exc:
        raise InvalidArchiveError(f"Not a valid ZIP archive: {project_path}") from exc
    except OSError as exc:
        raise InvalidArchiveError(f"Cannot read project archive: {project_path}") from exc

    try:
        document = json.loads(raw_manifest.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InvalidProjectError(f"Invalid UTF-8 JSON manifest: {exc}") from exc
    if not isinstance(document, dict):
        raise InvalidProjectError("Project manifest must be a JSON object")

    schema_version = document.get("schema_version")
    if not isinstance(schema_version, int):
        raise InvalidProjectError("Project manifest requires an integer schema_version")
    if schema_version > CURRENT_SCHEMA_VERSION:
        raise UnsupportedSchemaVersionError(
            f"Project schema {schema_version} is newer than supported schema "
            f"{CURRENT_SCHEMA_VERSION}"
        )
    if schema_version < CURRENT_SCHEMA_VERSION:
        document = registry.migrate(
            document,
            from_version=schema_version,
            target_version=CURRENT_SCHEMA_VERSION,
        )
    try:
        project = Project.model_validate(document)
    except ValidationError as exc:
        raise InvalidProjectError(
            "Project manifest failed schema validation",
            issues=pydantic_issues(exc),
        ) from exc

    issues = list(project_reference_issues(project))
    members = set(member_names)
    for index, asset in enumerate(project.assets):
        if asset.member_path not in members:
            issues.append(
                ValidationIssue(
                    code="missing_asset_member",
                    path=f"/assets/{index}/member_path",
                    message=f"Referenced archive member does not exist: {asset.member_path}",
                )
            )
    for track_index, track in enumerate(project.tracks):
        for effect_index, effect in enumerate(track.effects):
            if effect.state is None:
                continue
            if effect.state.member_path not in members:
                issues.append(
                    ValidationIssue(
                        code="missing_plugin_state_member",
                        path=f"/tracks/{track_index}/effects/{effect_index}/state/member_path",
                        message=(
                            "Referenced plugin state member does not exist: "
                            f"{effect.state.member_path}"
                        ),
                    )
                )
    if issues:
        raise ProjectValidationError(issues)
    return project, member_names


def _existing_asset_payloads(path: Path, project: Project) -> dict[str, bytes]:
    state_paths = [
        effect.state.member_path
        for track in project.tracks
        for effect in track.effects
        if effect.state is not None
    ]
    member_paths = [asset.member_path for asset in project.assets] + state_paths
    if not member_paths:
        return {}
    try:
        with ZipFile(path, mode="r") as archive:
            return {member_path: archive.read(member_path) for member_path in member_paths}
    except (BadZipFile, KeyError, OSError) as exc:
        raise InvalidArchiveError(f"Cannot preserve existing project assets: {path}") from exc


def create_project(
    path: Path | str,
    name: str,
    *,
    tempo_bpm: float = 120.0,
    sample_rate: int = 44100,
) -> Project:
    """Create a new empty project archive."""

    project_path = _project_path(path)
    if project_path.exists():
        raise ProjectArchiveError(f"Project already exists: {project_path}")
    project = new_project(name, tempo_bpm=tempo_bpm, sample_rate=sample_rate)
    _write_archive(project_path, project, {})
    return project


def load_project(
    path: Path | str,
    *,
    registry: MigrationRegistry = DEFAULT_REGISTRY,
) -> Project:
    """Load a project without rewriting it, applying migrations in memory."""

    project, _ = _read_archive_document(path, registry=registry)
    return project


def save_project(path: Path | str, project: Project) -> None:
    """Atomically save a project while preserving its existing asset bytes."""

    project_path = _project_path(path)
    issues = project_reference_issues(project)
    if issues:
        raise ProjectValidationError(issues)
    payloads = _existing_asset_payloads(project_path, project) if project_path.exists() else {}
    _write_archive(project_path, project, payloads)


def validate_project(
    path: Path | str,
    *,
    registry: MigrationRegistry = DEFAULT_REGISTRY,
) -> ValidationReport:
    """Validate the archive, manifest references, and asset hashes."""

    try:
        project, _ = _read_archive_document(path, registry=registry)
        project_path = _project_path(path)
        with ZipFile(project_path, mode="r") as archive:
            issues: list[ValidationIssue] = []
            for index, asset in enumerate(project.assets):
                payload = archive.read(asset.member_path)
                actual_hash = hashlib.sha256(payload).hexdigest()
                if len(payload) != asset.size_bytes:
                    issues.append(
                        ValidationIssue(
                            code="asset_size_mismatch",
                            path=f"/assets/{index}/size_bytes",
                            message=f"Expected {asset.size_bytes} bytes, found {len(payload)}",
                        )
                    )
                if actual_hash != asset.sha256:
                    issues.append(
                        ValidationIssue(
                            code="asset_hash_mismatch",
                            path=f"/assets/{index}/sha256",
                            message="Archive asset hash does not match the manifest.",
                        )
                    )
            for track_index, track in enumerate(project.tracks):
                for effect_index, effect in enumerate(track.effects):
                    if effect.state is None:
                        continue
                    payload = archive.read(effect.state.member_path)
                    actual_hash = hashlib.sha256(payload).hexdigest()
                    path = f"/tracks/{track_index}/effects/{effect_index}/state"
                    if len(payload) != effect.state.size_bytes:
                        issues.append(
                            ValidationIssue(
                                code="plugin_state_size_mismatch",
                                path=f"{path}/size_bytes",
                                message=(
                                    f"Expected {effect.state.size_bytes} bytes, "
                                    f"found {len(payload)}"
                                ),
                            )
                        )
                    if actual_hash != effect.state.sha256:
                        issues.append(
                            ValidationIssue(
                                code="plugin_state_hash_mismatch",
                                path=f"{path}/sha256",
                                message="Plugin state hash does not match the manifest.",
                            )
                        )
            return ValidationReport(issues)
    except ProjectArchiveError as exc:
        if isinstance(exc, ProjectValidationError):
            return ValidationReport(exc.issues)
        if isinstance(exc, InvalidProjectError) and exc.issues:
            return ValidationReport(exc.issues)
        return ValidationReport(
            [ValidationIssue(code=type(exc).__name__, path="/", message=str(exc))]
        )


def migrate_project(
    path: Path | str,
    *,
    registry: MigrationRegistry = DEFAULT_REGISTRY,
) -> Project:
    """Apply registered migrations and explicitly rewrite the archive."""

    project_path = _project_path(path)
    project = load_project(project_path, registry=registry)
    save_project(project_path, project)
    return project


def import_audio(path: Path | str, source: Path | str) -> AssetReference:
    """Copy an audio file into a project archive and register its metadata."""

    project_path = _project_path(path)
    source_path = Path(source)
    if not source_path.is_file():
        raise AssetImportError(f"Audio source does not exist: {source_path}")
    if not source_path.suffix:
        raise AssetImportError("Audio source must have a file extension")

    try:
        info = sf.info(str(source_path))
        payload = source_path.read_bytes()
    except (OSError, RuntimeError) as exc:
        raise AssetImportError(f"Could not read audio source: {source_path}") from exc

    project = load_project(project_path)
    asset_id = uuid4()
    member_path = f"{ASSET_PREFIX}{asset_id}{source_path.suffix.lower()}"
    asset = AssetReference(
        id=asset_id,
        member_path=member_path,
        original_name=source_path.name,
        size_bytes=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
        sample_rate=info.samplerate,
        channels=info.channels,
        frames=info.frames,
        format=info.format,
    )
    updated = project.model_copy(deep=True)
    updated.assets.append(asset)
    updated.revision.number += 1
    payloads = _existing_asset_payloads(project_path, project)
    payloads[member_path] = payload
    _write_archive(project_path, updated, payloads)
    return asset
