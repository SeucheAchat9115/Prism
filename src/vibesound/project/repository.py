"""Scalable working-project persistence and portable archive interchange."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from threading import RLock
from typing import Any, BinaryIO
from uuid import UUID, uuid4
from zipfile import ZIP_DEFLATED, ZIP_STORED, BadZipFile, ZipFile, ZipInfo

import portalocker
import soundfile as sf
from pydantic import ValidationError

from vibesound.project.archive import MANIFEST_MEMBER, PROJECT_SUFFIX, load_project
from vibesound.project.errors import (
    AssetImportError,
    ExternalProjectChangeError,
    InvalidArchiveError,
    InvalidProjectError,
    ProjectLockedError,
    ProjectResourceLimitError,
    ProjectValidationError,
    StagedUploadError,
    ValidationIssue,
    WorkingProjectError,
)
from vibesound.project.models import AssetReference, Project, new_project
from vibesound.project.validation import (
    LayeredValidationReport,
    ValidationStage,
    project_playback_issues,
    project_reference_issues,
    pydantic_issues,
)

WORKING_SUFFIX = ".vibesound-work"
WORKING_FORMAT_VERSION = 1
INTERNAL_DIRECTORY = ".vibesound"
ASSET_DIRECTORY = "assets/audio"
HISTORY_DIRECTORY = "history"
EXPORT_DIRECTORY = "exports"
_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
_COPY_CHUNK_BYTES = 1024 * 1024


@dataclass(frozen=True, slots=True)
class RepositoryLimits:
    """Resource limits applied before or during untrusted archive expansion."""

    max_archive_members: int = 10_000
    max_manifest_bytes: int = 16 * 1024 * 1024
    max_asset_bytes: int = 16 * 1024**3
    max_expanded_bytes: int = 64 * 1024**3
    max_compression_ratio: float = 1000.0
    max_staged_uploads: int = 16
    max_staged_bytes: int = 32 * 1024**3
    upload_ttl_seconds: int = 3600
    max_idempotency_records: int = 10_000
    idempotency_ttl_seconds: int = 30 * 24 * 3600


@dataclass(frozen=True, slots=True)
class SourceFingerprint:
    """Persisted identity used to detect changes to a source archive."""

    size_bytes: int
    modified_ns: int
    sha256: str


@dataclass(frozen=True, slots=True)
class RepositorySnapshot:
    """Immutable metadata and asset paths leased for background work."""

    project: Project
    working_path: Path
    asset_paths: Mapping[UUID, Path]


@dataclass(frozen=True, slots=True)
class StagedAudioUpload:
    """Validated audio stored outside the project until a transaction consumes it."""

    upload_id: UUID
    path: Path
    original_name: str
    size_bytes: int
    sha256: str
    sample_rate: int
    channels: int
    frames: int
    format: str
    suffix: str
    created_at: float
    expires_at: float

    def to_public_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["upload_id"] = str(self.upload_id)
        del value["path"]
        return value

    def to_storage_dict(self) -> dict[str, Any]:
        value = self.to_public_dict()
        value["path"] = str(self.path)
        return value


class ProjectRepository:
    """Own one writable working project and its portable archive relationship."""

    def __init__(
        self,
        working_path: Path,
        *,
        limits: RepositoryLimits | None = None,
    ) -> None:
        self._working_path = working_path
        self._limits = limits or RepositoryLimits()
        self._mutex = RLock()
        self._closed = False
        self._conflicted = False
        self._ensure_layout()
        self._lock = portalocker.Lock(
            str(self._lock_path),
            mode="a",
            timeout=0,
            fail_when_locked=True,
        )
        try:
            self._lock_handle = self._lock.acquire()
        except portalocker.exceptions.LockException as error:
            raise ProjectLockedError(
                f"Working project is already owned by another process: {working_path}"
            ) from error
        try:
            self._state = self._read_state()
            self._project = self._read_working_project()
            self._manifest_sha256 = _hash_file(self._manifest_path)
            self._cleanup_staging()
        except Exception:
            self._lock.release()
            raise

    @classmethod
    def open(
        cls,
        path: Path | str,
        *,
        limits: RepositoryLimits | None = None,
    ) -> "ProjectRepository":
        """Open a sidecar directly or import a portable archive transparently."""

        source = Path(path).resolve(strict=True)
        if source.is_dir():
            if source.suffix.lower() != WORKING_SUFFIX:
                raise WorkingProjectError(
                    f"Working project directory must end with {WORKING_SUFFIX}: {source}"
                )
            return cls(source, limits=limits)
        if source.suffix.lower() != PROJECT_SUFFIX:
            raise WorkingProjectError(f"Project path must end with {PROJECT_SUFFIX}: {source}")
        working = source.with_suffix(WORKING_SUFFIX)
        if not working.exists():
            _import_archive(source, working, limits or RepositoryLimits())
        repository = cls(working, limits=limits)
        repository._verify_source_identity(source)
        return repository

    @classmethod
    def create(
        cls,
        path: Path | str,
        name: str,
        *,
        tempo_bpm: float = 120.0,
        sample_rate: int = 44100,
        limits: RepositoryLimits | None = None,
    ) -> "ProjectRepository":
        """Create a new working project without first creating a ZIP archive."""

        working = Path(path).resolve(strict=False)
        if working.suffix.lower() != WORKING_SUFFIX:
            raise WorkingProjectError(
                f"Working project directory must end with {WORKING_SUFFIX}: {working}"
            )
        if working.exists():
            raise WorkingProjectError(f"Working project already exists: {working}")
        working.mkdir(parents=True)
        try:
            _create_layout(working)
            project = new_project(name, tempo_bpm=tempo_bpm, sample_rate=sample_rate)
            _atomic_json_write(working / MANIFEST_MEMBER, project.model_dump(mode="json"))
            _atomic_json_write(
                working / INTERNAL_DIRECTORY / "repository.json",
                {
                    "working_format_version": WORKING_FORMAT_VERSION,
                    "project_id": str(project.project_id),
                    "source_archive": None,
                    "source_fingerprint": None,
                },
            )
            _write_history(working, project.revision.number, {"kind": "created"})
        except Exception:
            shutil.rmtree(working, ignore_errors=True)
            raise
        return cls(working, limits=limits)

    @property
    def working_path(self) -> Path:
        return self._working_path

    @property
    def source_archive(self) -> Path | None:
        value = self._state.get("source_archive")
        return None if value is None else Path(value)

    @property
    def exports_path(self) -> Path:
        return self._working_path / EXPORT_DIRECTORY

    @property
    def jobs_path(self) -> Path:
        return self._working_path / INTERNAL_DIRECTORY / "jobs"

    @property
    def conflicted(self) -> bool:
        return self._conflicted

    def get_project(self) -> Project:
        with self._mutex:
            self._require_open()
            return self._project.model_copy(deep=True)

    def snapshot(self) -> RepositorySnapshot:
        with self._mutex:
            self._require_open()
            project = self._project.model_copy(deep=True)
            paths = {asset.id: self.asset_path(asset) for asset in project.assets}
            return RepositorySnapshot(project, self._working_path, paths)

    def validation_report(self) -> LayeredValidationReport:
        """Run explicit layered validation, including asset hashes and decodability."""

        with self._mutex:
            self._require_open()
            archive_issues: list[ValidationIssue] = []
            try:
                self.check_external_changes()
            except ExternalProjectChangeError as error:
                archive_issues.append(
                    ValidationIssue(
                        code="external_project_change",
                        path="/",
                        message=str(error),
                    )
                )
            playback_issues = list(project_playback_issues(self._project))
            for index, asset in enumerate(self._project.assets):
                path = self.asset_path(asset)
                try:
                    if path.stat().st_size != asset.size_bytes:
                        playback_issues.append(
                            ValidationIssue(
                                code="asset_size_mismatch",
                                path=f"/assets/{index}/size_bytes",
                                message="Working asset size does not match the manifest.",
                            )
                        )
                    if _hash_file(path) != asset.sha256:
                        playback_issues.append(
                            ValidationIssue(
                                code="asset_hash_mismatch",
                                path=f"/assets/{index}/sha256",
                                message="Working asset hash does not match the manifest.",
                            )
                        )
                    info = sf.info(str(path))
                    if (
                        int(info.samplerate) != asset.sample_rate
                        or int(info.channels) != asset.channels
                        or int(info.frames) != asset.frames
                    ):
                        playback_issues.append(
                            ValidationIssue(
                                code="decoded_metadata_mismatch",
                                path=f"/assets/{index}",
                                message="Decoded audio metadata does not match the manifest.",
                            )
                        )
                except (OSError, RuntimeError, ValueError) as error:
                    playback_issues.append(
                        ValidationIssue(
                            code="asset_not_decodable",
                            path=f"/assets/{index}/member_path",
                            message=f"Working audio asset is not decodable: {error}",
                        )
                    )
            return LayeredValidationReport(
                {
                    ValidationStage.ARCHIVE_INTEGRITY: archive_issues,
                    ValidationStage.SCHEMA: (),
                    ValidationStage.PROJECT_REFERENCES: project_reference_issues(
                        self._project
                    ),
                    ValidationStage.PLAYBACK_READINESS: playback_issues,
                    ValidationStage.DEVICE_COMPATIBILITY: (),
                }
            )

    def asset_path(self, asset: AssetReference) -> Path:
        path = (self._working_path / PurePosixPath(asset.member_path)).resolve(strict=False)
        if not path.is_relative_to(self._working_path):
            raise InvalidArchiveError(f"Unsafe working asset path: {asset.member_path}")
        return path

    def commit_project(self, candidate: Project, *, history: Mapping[str, Any]) -> Project:
        """Atomically commit validated metadata as the next project revision."""

        with self._mutex:
            self._require_writable()
            self.check_external_changes()
            if candidate.project_id != self._project.project_id:
                raise WorkingProjectError("Candidate belongs to another project")
            expected_revision = self._project.revision.number + 1
            if candidate.revision.number != expected_revision:
                raise WorkingProjectError(
                    "Candidate revision must be "
                    f"{expected_revision}, got {candidate.revision.number}"
                )
            issues = project_reference_issues(candidate)
            if issues:
                raise ProjectValidationError(issues)
            missing = [
                asset.member_path
                for asset in candidate.assets
                if not self.asset_path(asset).is_file()
            ]
            if missing:
                raise WorkingProjectError(f"Candidate references missing assets: {missing[0]}")
            history_document = dict(history)
            history_document.update(
                {
                    "revision": candidate.revision.number,
                    "project_id": str(candidate.project_id),
                    "committed_at": time.time(),
                }
            )
            _write_history(self._working_path, candidate.revision.number, history_document)
            _atomic_json_write(self._manifest_path, candidate.model_dump(mode="json"))
            self._project = candidate.model_copy(deep=True)
            self._manifest_sha256 = _hash_file(self._manifest_path)
            return self._project.model_copy(deep=True)

    def stage_audio(self, stream: BinaryIO, original_name: str) -> StagedAudioUpload:
        """Stream, bound, hash, and inspect one audio upload without changing revision."""

        with self._mutex:
            self._require_writable()
            self._cleanup_staging()
            uploads = list(self._iter_upload_metadata())
            if len(uploads) >= self._limits.max_staged_uploads:
                raise ProjectResourceLimitError("Too many staged uploads")
            staged_total = sum(upload.size_bytes for upload in uploads)
            if staged_total >= self._limits.max_staged_bytes:
                raise ProjectResourceLimitError("Staged upload storage is full")
            suffix = Path(original_name).suffix.lower()
            if suffix not in {".wav", ".aif", ".aiff"}:
                raise AssetImportError("Audio uploads must be WAV or AIFF files")
            upload_id = uuid4()
            data_path = self._staging_path / f"{upload_id}{suffix}"
            digest = hashlib.sha256()
            size = 0
            try:
                with data_path.open("xb") as destination:
                    while True:
                        chunk = stream.read(_COPY_CHUNK_BYTES)
                        if not chunk:
                            break
                        size += len(chunk)
                        if size > self._limits.max_asset_bytes:
                            raise ProjectResourceLimitError("Audio upload exceeds the asset limit")
                        if staged_total + size > self._limits.max_staged_bytes:
                            raise ProjectResourceLimitError("Staged upload storage is full")
                        digest.update(chunk)
                        destination.write(chunk)
                    destination.flush()
                    os.fsync(destination.fileno())
                info = sf.info(str(data_path))
                if info.channels not in (1, 2) or info.frames <= 0:
                    raise AssetImportError("Audio must contain non-empty mono or stereo samples")
            except Exception:
                data_path.unlink(missing_ok=True)
                raise
            now = time.time()
            upload = StagedAudioUpload(
                upload_id=upload_id,
                path=data_path,
                original_name=Path(original_name).name,
                size_bytes=size,
                sha256=digest.hexdigest(),
                sample_rate=int(info.samplerate),
                channels=int(info.channels),
                frames=int(info.frames),
                format=str(info.format),
                suffix=suffix,
                created_at=now,
                expires_at=now + self._limits.upload_ttl_seconds,
            )
            _atomic_json_write(self._upload_metadata_path(upload_id), upload.to_storage_dict())
            return upload

    def get_upload(self, upload_id: UUID) -> StagedAudioUpload:
        with self._mutex:
            self._require_open()
            metadata_path = self._upload_metadata_path(upload_id)
            if not metadata_path.is_file():
                raise StagedUploadError(f"Staged upload does not exist: {upload_id}")
            upload = _load_upload(metadata_path)
            if upload.expires_at <= time.time() or not upload.path.is_file():
                self.discard_upload(upload_id)
                raise StagedUploadError(f"Staged upload expired: {upload_id}")
            return upload

    def install_upload(self, upload_id: UUID, asset_id: UUID) -> tuple[AssetReference, Path]:
        """Install immutable uploaded bytes before their metadata commit point."""

        with self._mutex:
            upload = self.get_upload(upload_id)
            member_path = f"{ASSET_DIRECTORY}/{asset_id}{upload.suffix}"
            destination = self._working_path / PurePosixPath(member_path)
            if destination.exists():
                raise WorkingProjectError(f"Asset path already exists: {destination}")
            temporary = _temporary_sibling(destination)
            try:
                with upload.path.open("rb") as source, temporary.open("xb") as output:
                    shutil.copyfileobj(source, output, length=_COPY_CHUNK_BYTES)
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temporary, destination)
            except Exception:
                temporary.unlink(missing_ok=True)
                raise
            return (
                AssetReference(
                    id=asset_id,
                    member_path=member_path,
                    original_name=upload.original_name,
                    size_bytes=upload.size_bytes,
                    sha256=upload.sha256,
                    sample_rate=upload.sample_rate,
                    channels=upload.channels,
                    frames=upload.frames,
                    format=upload.format,
                ),
                destination,
            )

    def rollback_installs(self, installs: list[tuple[UUID, UUID]]) -> None:
        """Remove asset copies installed for a metadata commit that did not succeed."""

        with self._mutex:
            for upload_id, asset_id in installs:
                try:
                    upload = self.get_upload(upload_id)
                except StagedUploadError:
                    continue
                path = self._working_path / ASSET_DIRECTORY / f"{asset_id}{upload.suffix}"
                path.unlink(missing_ok=True)

    def discard_upload(self, upload_id: UUID) -> None:
        with self._mutex:
            metadata = self._upload_metadata_path(upload_id)
            if metadata.is_file():
                try:
                    _load_upload(metadata).path.unlink(missing_ok=True)
                except (OSError, ValueError):
                    pass
                metadata.unlink(missing_ok=True)

    def get_idempotency(self, key: str) -> dict[str, Any] | None:
        """Return one live persisted idempotency record."""

        with self._mutex:
            self._require_open()
            ledger = self._read_idempotency()
            record = ledger.get(key)
            if record is None:
                return None
            if float(record.get("expires_at", 0)) <= time.time():
                del ledger[key]
                _atomic_json_write(self._idempotency_path, ledger)
                return None
            return dict(record)

    def put_idempotency(
        self,
        key: str,
        request_sha256: str,
        result: Mapping[str, Any],
    ) -> None:
        """Persist a bounded successful mutation result for safe client retries."""

        with self._mutex:
            self._require_writable()
            now = time.time()
            ledger = {
                item_key: value
                for item_key, value in self._read_idempotency().items()
                if float(value.get("expires_at", 0)) > now
            }
            ledger[key] = {
                "request_sha256": request_sha256,
                "result": dict(result),
                "created_at": now,
                "expires_at": now + self._limits.idempotency_ttl_seconds,
            }
            if len(ledger) > self._limits.max_idempotency_records:
                ordered = sorted(
                    ledger,
                    key=lambda item_key: float(ledger[item_key].get("created_at", 0)),
                )
                for item_key in ordered[: len(ledger) - self._limits.max_idempotency_records]:
                    del ledger[item_key]
            _atomic_json_write(self._idempotency_path, ledger)

    def write_job_metadata(self, job_id: UUID, document: Mapping[str, Any]) -> None:
        """Atomically persist one background-job status document."""

        with self._mutex:
            self._require_open()
            _atomic_json_write(self.jobs_path / f"{job_id}.json", document)

    def delete_job_metadata(self, job_id: UUID) -> None:
        """Remove expired terminal job metadata without touching its exported output."""

        with self._mutex:
            self._require_open()
            (self.jobs_path / f"{job_id}.json").unlink(missing_ok=True)

    def read_job_metadata(self) -> list[dict[str, Any]]:
        """Read retained job documents, ignoring no malformed state silently."""

        with self._mutex:
            self._require_open()
            documents: list[dict[str, Any]] = []
            for path in sorted(self.jobs_path.glob("*.json")):
                try:
                    value = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as error:
                    raise WorkingProjectError(
                        f"Background job metadata is invalid: {path.name}"
                    ) from error
                if not isinstance(value, dict):
                    raise WorkingProjectError(
                        f"Background job metadata must be an object: {path.name}"
                    )
                documents.append(value)
            return documents

    def check_external_changes(self) -> None:
        """Pause writes if the source archive or working manifest changed externally."""

        with self._mutex:
            self._require_open()
            if _hash_file(self._manifest_path) != self._manifest_sha256:
                self._conflicted = True
                raise ExternalProjectChangeError("Working project manifest changed externally")
            source = self.source_archive
            fingerprint = self._source_fingerprint
            if source is None or fingerprint is None:
                return
            if not source.is_file():
                self._conflicted = True
                raise ExternalProjectChangeError("Portable source archive was removed")
            stat = source.stat()
            changed = (
                stat.st_size != fingerprint.size_bytes
                or stat.st_mtime_ns != fingerprint.modified_ns
            )
            if changed:
                self._conflicted = True
                raise ExternalProjectChangeError("Portable source archive changed externally")

    def detach_source(self) -> None:
        """Keep working state and acknowledge an external source conflict."""

        with self._mutex:
            self._require_open()
            self._state["source_archive"] = None
            self._state["source_fingerprint"] = None
            _atomic_json_write(self._state_path, self._state)
            self._conflicted = False

    def resolve_output(self, relative_path: Path | str) -> Path:
        value = Path(relative_path)
        if value.is_absolute():
            raise WorkingProjectError("Output paths must be relative to the project export root")
        output = (self.exports_path / value).resolve(strict=False)
        export_root = self.exports_path.resolve(strict=False)
        if not output.is_relative_to(export_root):
            raise WorkingProjectError("Output path escapes the project export root")
        return output

    def export_archive(self, output: Path | str) -> tuple[Path, str]:
        """Stream a deterministic portable archive from a stable repository snapshot."""

        with self._mutex:
            self._require_open()
            snapshot = self.snapshot()
        return self.export_snapshot(snapshot, output)

    def export_snapshot(
        self,
        snapshot: RepositorySnapshot,
        output: Path | str,
    ) -> tuple[Path, str]:
        """Export exactly the captured revision, even if later commits are accepted."""

        if snapshot.working_path.resolve(strict=False) != self._working_path.resolve(
            strict=False
        ):
            raise WorkingProjectError("Repository snapshot belongs to another working project")
        history_paths = sorted(
            path
            for path in (self._working_path / HISTORY_DIRECTORY).glob("*.json")
            if int(path.stem) <= snapshot.project.revision.number
        )
        destination = self.resolve_output(output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = _temporary_sibling(destination)
        try:
            with ZipFile(temporary, "w", allowZip64=True) as archive:
                _zip_write_bytes(
                    archive,
                    MANIFEST_MEMBER,
                    _json_bytes(snapshot.project.model_dump(mode="json")),
                    compression=ZIP_DEFLATED,
                )
                for history_path in history_paths:
                    _zip_copy_file(
                        archive,
                        f"{HISTORY_DIRECTORY}/{history_path.name}",
                        history_path,
                        compression=ZIP_DEFLATED,
                    )
                for asset in sorted(snapshot.project.assets, key=lambda item: item.member_path):
                    _zip_copy_file(
                        archive,
                        asset.member_path,
                        snapshot.asset_paths[asset.id],
                        compression=ZIP_STORED,
                    )
            _fsync_file(temporary)
            os.replace(temporary, destination)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        return destination, _hash_file(destination)

    def close(self) -> None:
        with self._mutex:
            if self._closed:
                return
            self._closed = True
            self._lock.release()

    def __enter__(self) -> "ProjectRepository":
        self._require_open()
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()

    @property
    def _manifest_path(self) -> Path:
        return self._working_path / MANIFEST_MEMBER

    @property
    def _state_path(self) -> Path:
        return self._working_path / INTERNAL_DIRECTORY / "repository.json"

    @property
    def _lock_path(self) -> Path:
        return self._working_path / INTERNAL_DIRECTORY / "lock"

    @property
    def _staging_path(self) -> Path:
        return self._working_path / INTERNAL_DIRECTORY / "staging"

    @property
    def _idempotency_path(self) -> Path:
        return self._working_path / INTERNAL_DIRECTORY / "idempotency.json"

    @property
    def _source_fingerprint(self) -> SourceFingerprint | None:
        value = self._state.get("source_fingerprint")
        return None if value is None else SourceFingerprint(**value)

    def _read_state(self) -> dict[str, Any]:
        try:
            value = json.loads(self._state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise WorkingProjectError("Working repository metadata is invalid") from error
        if not isinstance(value, dict):
            raise WorkingProjectError("Working repository metadata must be a JSON object")
        if value.get("working_format_version") != WORKING_FORMAT_VERSION:
            raise WorkingProjectError("Unsupported working-project format")
        return value

    def _read_working_project(self) -> Project:
        try:
            document = json.loads(self._manifest_path.read_text(encoding="utf-8"))
            project = Project.model_validate(document)
        except OSError as error:
            raise WorkingProjectError("Could not read working project manifest") from error
        except json.JSONDecodeError as error:
            raise InvalidProjectError("Working project manifest is invalid JSON") from error
        except ValidationError as error:
            raise InvalidProjectError(
                "Working project manifest failed schema validation",
                issues=pydantic_issues(error),
            ) from error
        issues = project_reference_issues(project)
        if issues:
            raise ProjectValidationError(issues)
        for asset in project.assets:
            if not self.asset_path(asset).is_file():
                raise ProjectValidationError(
                    [
                        ValidationIssue(
                            code="missing_asset_member",
                            path=f"/assets/{asset.id}/member_path",
                            message=f"Working asset is missing: {asset.member_path}",
                        )
                    ]
                )
        return project

    def _verify_source_identity(self, source: Path) -> None:
        recorded = self.source_archive
        if recorded is None or recorded.resolve(strict=False) != source.resolve(strict=False):
            self.close()
            raise WorkingProjectError("Working sidecar belongs to a different source archive")
        self.check_external_changes()

    def _ensure_layout(self) -> None:
        if not self._working_path.is_dir():
            raise WorkingProjectError(f"Working project does not exist: {self._working_path}")
        _create_layout(self._working_path)
        if not self._manifest_path.is_file() or not self._state_path.is_file():
            raise WorkingProjectError(f"Incomplete working project: {self._working_path}")

    def _upload_metadata_path(self, upload_id: UUID) -> Path:
        return self._staging_path / f"{upload_id}.json"

    def _iter_upload_metadata(self) -> Iterator[StagedAudioUpload]:
        for path in self._staging_path.glob("*.json"):
            try:
                yield _load_upload(path)
            except (OSError, ValueError):
                path.unlink(missing_ok=True)

    def _read_idempotency(self) -> dict[str, Any]:
        if not self._idempotency_path.is_file():
            return {}
        try:
            value = json.loads(self._idempotency_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise WorkingProjectError("Idempotency ledger is invalid") from error
        if not isinstance(value, dict):
            raise WorkingProjectError("Idempotency ledger must be a JSON object")
        return value

    def _cleanup_staging(self) -> None:
        now = time.time()
        for upload in tuple(self._iter_upload_metadata()):
            if upload.expires_at <= now or not upload.path.is_file():
                self.discard_upload(upload.upload_id)

    def _require_open(self) -> None:
        if self._closed:
            raise WorkingProjectError("Project repository is closed")

    def _require_writable(self) -> None:
        self._require_open()
        if self._conflicted:
            raise ExternalProjectChangeError("Project writes are paused after an external change")


def working_path_for_archive(path: Path | str) -> Path:
    archive = Path(path)
    if archive.suffix.lower() != PROJECT_SUFFIX:
        raise WorkingProjectError(f"Project path must end with {PROJECT_SUFFIX}: {archive}")
    return archive.with_suffix(WORKING_SUFFIX)


def _create_layout(working: Path) -> None:
    (working / ASSET_DIRECTORY).mkdir(parents=True, exist_ok=True)
    (working / HISTORY_DIRECTORY).mkdir(parents=True, exist_ok=True)
    (working / EXPORT_DIRECTORY).mkdir(parents=True, exist_ok=True)
    internal = working / INTERNAL_DIRECTORY
    (internal / "staging").mkdir(parents=True, exist_ok=True)
    (internal / "cache" / "audio").mkdir(parents=True, exist_ok=True)
    (internal / "jobs").mkdir(parents=True, exist_ok=True)


def _import_archive(source: Path, working: Path, limits: RepositoryLimits) -> None:
    temporary = working.with_name(f".{working.name}.{uuid4().hex}.tmp")
    if temporary.exists():
        raise WorkingProjectError(f"Temporary working path already exists: {temporary}")
    temporary.mkdir(parents=True)
    try:
        _create_layout(temporary)
        _validate_archive_limits(source, limits)
        project = load_project(source)
        with ZipFile(source, "r") as archive:
            for asset in project.assets:
                destination = temporary / PurePosixPath(asset.member_path)
                destination.parent.mkdir(parents=True, exist_ok=True)
                digest = hashlib.sha256()
                size = 0
                try:
                    with archive.open(asset.member_path, "r") as member, destination.open(
                        "xb"
                    ) as output:
                        while True:
                            chunk = member.read(_COPY_CHUNK_BYTES)
                            if not chunk:
                                break
                            size += len(chunk)
                            if size > limits.max_asset_bytes:
                                raise ProjectResourceLimitError(
                                    f"Archive asset exceeds limit: {asset.member_path}"
                                )
                            digest.update(chunk)
                            output.write(chunk)
                        output.flush()
                        os.fsync(output.fileno())
                except KeyError as error:
                    raise InvalidArchiveError(
                        f"Archive asset is missing: {asset.member_path}"
                    ) from error
                if size != asset.size_bytes or digest.hexdigest() != asset.sha256:
                    raise InvalidArchiveError(
                        f"Archive asset integrity mismatch: {asset.member_path}"
                    )
        _atomic_json_write(temporary / MANIFEST_MEMBER, project.model_dump(mode="json"))
        fingerprint = _fingerprint(source)
        _atomic_json_write(
            temporary / INTERNAL_DIRECTORY / "repository.json",
            {
                "working_format_version": WORKING_FORMAT_VERSION,
                "project_id": str(project.project_id),
                "source_archive": str(source),
                "source_fingerprint": asdict(fingerprint),
            },
        )
        _write_history(
            temporary,
            project.revision.number,
            {"kind": "portable_archive_import", "revision": project.revision.number},
        )
        os.replace(temporary, working)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def _validate_archive_limits(path: Path, limits: RepositoryLimits) -> None:
    try:
        with ZipFile(path, "r") as archive:
            members = archive.infolist()
            if len(members) > limits.max_archive_members:
                raise ProjectResourceLimitError("Portable archive contains too many members")
            seen: set[str] = set()
            expanded_total = 0
            for info in members:
                _validate_member_name(info.filename)
                normalized = info.filename.casefold()
                if normalized in seen:
                    raise InvalidArchiveError(
                        f"Duplicate or case-colliding archive member: {info.filename}"
                    )
                seen.add(normalized)
                if info.flag_bits & 0x1:
                    raise InvalidArchiveError(
                        f"Encrypted ZIP members are not allowed: {info.filename}"
                    )
                mode = (info.external_attr >> 16) & 0xF000
                if mode == 0xA000:
                    raise InvalidArchiveError(f"ZIP symlinks are not allowed: {info.filename}")
                if info.filename == MANIFEST_MEMBER and info.file_size > limits.max_manifest_bytes:
                    raise ProjectResourceLimitError("Portable project manifest is too large")
                if info.filename.startswith(f"{ASSET_DIRECTORY}/"):
                    if info.file_size > limits.max_asset_bytes:
                        raise ProjectResourceLimitError(
                            f"Portable asset exceeds size limit: {info.filename}"
                        )
                    ratio = info.file_size / max(info.compress_size, 1)
                    if ratio > limits.max_compression_ratio:
                        raise ProjectResourceLimitError(
                            f"Portable asset compression ratio is unsafe: {info.filename}"
                        )
                expanded_total += info.file_size
                if expanded_total > limits.max_expanded_bytes:
                    raise ProjectResourceLimitError(
                        "Portable archive expands beyond the total limit"
                    )
            if MANIFEST_MEMBER.casefold() not in seen:
                raise InvalidArchiveError(f"Archive is missing {MANIFEST_MEMBER}")
    except BadZipFile as error:
        raise InvalidArchiveError(f"Not a valid ZIP archive: {path}") from error


def _validate_member_name(name: str) -> None:
    path = PurePosixPath(name)
    if (
        not name
        or len(name.encode("utf-8")) > 512
        or "\\" in name
        or "\x00" in name
        or ":" in name
        or path.is_absolute()
        or ".." in path.parts
        or name.endswith("/")
    ):
        raise InvalidArchiveError(f"Unsafe archive member path: {name!r}")


def _fingerprint(path: Path) -> SourceFingerprint:
    stat = path.stat()
    return SourceFingerprint(stat.st_size, stat.st_mtime_ns, _hash_file(path))


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(_COPY_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )


def _atomic_json_write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = _temporary_sibling(path)
    try:
        with temporary.open("xb") as output:
            output.write(_json_bytes(value))
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _write_history(working: Path, revision: int, value: Mapping[str, Any]) -> None:
    path = working / HISTORY_DIRECTORY / f"{revision:020d}.json"
    _atomic_json_write(path, value)


def _temporary_sibling(path: Path) -> Path:
    handle, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    os.close(handle)
    temporary = Path(name)
    temporary.unlink()
    return temporary


def _fsync_file(path: Path) -> None:
    with path.open("r+b") as handle:
        handle.flush()
        os.fsync(handle.fileno())


def _zip_info(name: str, compression: int) -> ZipInfo:
    info = ZipInfo(name, _ZIP_TIMESTAMP)
    info.compress_type = compression
    info.create_system = 0
    info.external_attr = 0
    info.flag_bits |= 0x800
    return info


def _zip_write_bytes(archive: ZipFile, name: str, payload: bytes, *, compression: int) -> None:
    archive.writestr(_zip_info(name, compression), payload, compresslevel=9)


def _zip_copy_file(archive: ZipFile, name: str, source: Path, *, compression: int) -> None:
    info = _zip_info(name, compression)
    info.file_size = source.stat().st_size
    with source.open("rb") as input_file, archive.open(info, "w", force_zip64=True) as output:
        shutil.copyfileobj(input_file, output, length=_COPY_CHUNK_BYTES)


def _load_upload(path: Path) -> StagedAudioUpload:
    document = json.loads(path.read_text(encoding="utf-8"))
    document["upload_id"] = UUID(document["upload_id"])
    document["path"] = Path(document["path"])
    return StagedAudioUpload(**document)


@contextmanager
def open_repository(path: Path | str) -> Iterator[ProjectRepository]:
    """Context-manager convenience for compatibility callers."""

    repository = ProjectRepository.open(path)
    try:
        yield repository
    finally:
        repository.close()
