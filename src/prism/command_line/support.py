"""Stable output, validation, and service-connection helpers for the CLI."""

from __future__ import annotations

import ipaddress
import json
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import Any, Literal, TypeVar, cast
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

import typer
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from prism.api import PrismClient, PrismClientError
from prism.application import ApiIssue, BackgroundJob, ReadinessResult, TransactionRequest
from prism.application.errors import ApplicationError
from prism.project import (
    ExternalProjectChangeError,
    InvalidArchiveError,
    InvalidProjectError,
    Project,
    ProjectArchiveError,
    ProjectLockedError,
    ProjectValidationError,
    WorkingProjectError,
    load_project,
    working_path_for_archive,
)

CLI_SCHEMA_VERSION = 1
DEFAULT_SERVICE_URL = "http://127.0.0.1:8765"
MAX_INPUT_BYTES = 16 * 1024 * 1024
_ENTITY_TYPES = frozenset({"track", "scene", "clip", "asset", "slot"})
_NAMED_ENTITY_TYPES = _ENTITY_TYPES - {"slot"}
T = TypeVar("T")


class CliExit(IntEnum):
    """Stable process exit statuses for agent-facing commands."""

    SUCCESS = 0
    USAGE = 2
    VALIDATION = 3
    CONFLICT = 4
    IO = 5
    SERVICE = 6
    AUDIO = 7
    JOB = 8
    INTERNAL = 70
    INTERRUPTED = 130


class ProjectContext(BaseModel):
    """Project identity attached to every project-scoped JSON envelope."""

    model_config = ConfigDict(extra="forbid")

    path: str
    id: UUID
    revision: int = Field(ge=0)


class CliEnvelope(BaseModel):
    """Versioned machine-output contract shared by all finite CLI commands."""

    model_config = ConfigDict(extra="forbid")

    cli_schema_version: Literal[1] = 1
    ok: bool
    command: str
    project: ProjectContext | None = None
    dry_run: bool = False
    data: Any = None
    warnings: list[ApiIssue] = Field(default_factory=list)
    errors: list[ApiIssue] = Field(default_factory=list)


@dataclass(slots=True)
class CommandResult:
    """One successful command result before human or JSON rendering."""

    data: Any = None
    project: ProjectContext | None = None
    human: tuple[str, ...] = ()
    warnings: list[ApiIssue] = field(default_factory=list)


class CliFailure(Exception):
    """A known CLI failure with a stable exit class and structured issues."""

    def __init__(
        self,
        exit_code: CliExit,
        issues: list[ApiIssue] | tuple[ApiIssue, ...] | ApiIssue,
        *,
        project: ProjectContext | None = None,
        data: Any = None,
    ) -> None:
        if isinstance(issues, ApiIssue):
            issues = [issues]
        self.exit_code = exit_code
        self.issues = list(issues)
        self.project = project
        self.data = data
        super().__init__("; ".join(issue.message for issue in self.issues))


@dataclass(frozen=True, slots=True)
class LocalProject:
    """Read-only identity obtained without taking the repository writer lock."""

    path: Path
    project: Project


@dataclass(frozen=True, slots=True)
class ServiceProject:
    """Verified client connection to the service owning one local project."""

    client: PrismClient
    local: LocalProject
    readiness: ReadinessResult

    @property
    def context(self) -> ProjectContext:
        return ProjectContext(
            path=str(self.local.path),
            id=self.readiness.project_id,
            revision=self.readiness.revision,
        )


def run_command(
    command: str,
    *,
    as_json: bool,
    dry_run: bool = False,
    action: Callable[[], CommandResult],
) -> None:
    """Execute a finite command and normalize all expected failure families."""

    try:
        result = action()
    except CliFailure as error:
        _emit_failure(command, as_json, dry_run, error)
    except PrismClientError as error:
        failure = CliFailure(_client_exit(error), error.issues)
        _emit_failure(command, as_json, dry_run, failure)
    except ApplicationError as error:
        issue = ApiIssue(code=error.code, path=error.path, message=error.message)
        failure = CliFailure(_status_exit(error.status_code, {error.code}), issue)
        _emit_failure(command, as_json, dry_run, failure)
    except ValidationError as error:
        issues = [
            ApiIssue(
                code="invalid_input",
                path="/" + "/".join(str(part) for part in item["loc"]),
                message=str(item["msg"]),
            )
            for item in error.errors()
        ]
        _emit_failure(command, as_json, dry_run, CliFailure(CliExit.USAGE, issues))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        issue = ApiIssue(code="invalid_json", message=str(error))
        _emit_failure(command, as_json, dry_run, CliFailure(CliExit.USAGE, issue))
    except (ProjectLockedError, ExternalProjectChangeError) as error:
        issue = ApiIssue(code="project_conflict", message=str(error))
        _emit_failure(command, as_json, dry_run, CliFailure(CliExit.CONFLICT, issue))
    except (InvalidArchiveError, InvalidProjectError, ProjectValidationError) as error:
        issues = _project_issues(error)
        _emit_failure(command, as_json, dry_run, CliFailure(CliExit.VALIDATION, issues))
    except (ProjectArchiveError, WorkingProjectError, OSError) as error:
        issue = ApiIssue(code="io_error", message=str(error))
        _emit_failure(command, as_json, dry_run, CliFailure(CliExit.IO, issue))
    except KeyboardInterrupt:
        issue = ApiIssue(code="interrupted", message="Command interrupted")
        _emit_failure(command, as_json, dry_run, CliFailure(CliExit.INTERRUPTED, issue))
    except Exception as error:  # pragma: no cover - defensive CLI boundary
        issue = ApiIssue(code="internal_error", message=str(error) or type(error).__name__)
        _emit_failure(command, as_json, dry_run, CliFailure(CliExit.INTERNAL, issue))
    else:
        _emit_success(command, as_json, dry_run, result)


def emit_stream_failure(command: str, as_json: bool, error: BaseException) -> None:
    """Normalize a failure from a streaming command and terminate the process."""

    if isinstance(error, CliFailure):
        failure = error
    elif isinstance(error, PrismClientError):
        failure = CliFailure(_client_exit(error), error.issues)
    elif isinstance(error, TimeoutError):
        failure = CliFailure(
            CliExit.JOB,
            ApiIssue(code="event_timeout", message="No event arrived before the timeout"),
        )
    elif isinstance(error, KeyboardInterrupt):
        failure = CliFailure(
            CliExit.INTERRUPTED,
            ApiIssue(code="interrupted", message="Event watch interrupted"),
        )
    else:
        failure = CliFailure(
            CliExit.SERVICE,
            ApiIssue(code="event_stream_error", message=str(error)),
        )
    _emit_failure(command, as_json, False, failure)


def validate_service_url(value: str) -> str:
    """Accept HTTP(S) URLs only when they point at a loopback host."""

    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as error:
        raise CliFailure(
            CliExit.USAGE,
            ApiIssue(code="invalid_service_url", path="/url", message=str(error)),
        ) from error
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise CliFailure(
            CliExit.USAGE,
            ApiIssue(
                code="invalid_service_url",
                path="/url",
                message="Service URL must be an absolute HTTP or HTTPS URL",
            ),
        )
    if parsed.username is not None or parsed.password is not None:
        raise CliFailure(
            CliExit.USAGE,
            ApiIssue(
                code="invalid_service_url",
                path="/url",
                message="Service URL must not include credentials",
            ),
        )
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise CliFailure(
            CliExit.USAGE,
            ApiIssue(
                code="invalid_service_url",
                path="/url",
                message="Service URL must not include a path, query, or fragment",
            ),
        )
    if not _is_loopback(parsed.hostname):
        raise CliFailure(
            CliExit.USAGE,
            ApiIssue(
                code="non_loopback_service",
                path="/url",
                message="Prism CLI connections are restricted to loopback hosts",
            ),
        )
    host = parsed.hostname
    assert host is not None
    rendered_host = f"[{host}]" if ":" in host else host
    netloc = rendered_host if port is None else f"{rendered_host}:{port}"
    return urlunsplit((parsed.scheme, netloc, "", "", ""))


def read_local_project(path: Path | str) -> LocalProject:
    """Read a portable archive or working manifest without opening a writer."""

    requested = Path(path)
    try:
        resolved = requested.resolve(strict=True)
    except OSError as error:
        raise CliFailure(
            CliExit.VALIDATION,
            ApiIssue(code="project_not_found", path="/project", message=str(error)),
        ) from error
    if resolved.is_dir():
        if resolved.suffix.casefold() != ".prism-work":
            raise CliFailure(
                CliExit.VALIDATION,
                ApiIssue(
                    code="invalid_project_path",
                    path="/project",
                    message="Working project directories must end with .prism-work",
                ),
            )
        project = _read_working_manifest(resolved)
    elif resolved.suffix.casefold() == ".prism":
        sidecar = working_path_for_archive(resolved)
        project = _read_working_manifest(sidecar) if sidecar.is_dir() else load_project(resolved)
    else:
        raise CliFailure(
            CliExit.VALIDATION,
            ApiIssue(
                code="invalid_project_path",
                path="/project",
                message="Project must be a .prism archive or .prism-work directory",
            ),
        )
    return LocalProject(path=resolved, project=project)


@contextmanager
def connected_project(
    path: Path | str,
    url: str,
    *,
    timeout: float = 30.0,
) -> Iterator[ServiceProject]:
    """Connect and prove that the service owns the project named on the command line."""

    local = read_local_project(path)
    normalized_url = validate_service_url(url)
    local_context = ProjectContext(
        path=str(local.path),
        id=local.project.project_id,
        revision=local.project.revision.number,
    )
    try:
        with PrismClient(normalized_url, timeout=timeout) as client:
            readiness = client.readiness()
            if readiness.project_id != local.project.project_id:
                raise CliFailure(
                    CliExit.CONFLICT,
                    ApiIssue(
                        code="project_mismatch",
                        path="/project",
                        message=(
                            f"Service owns project {readiness.project_id}, but {local.path} "
                            f"contains {local.project.project_id}"
                        ),
                    ),
                    project=local_context,
                )
            service = ServiceProject(client=client, local=local, readiness=readiness)
            try:
                yield service
            except PrismClientError as error:
                raise CliFailure(
                    _client_exit(error),
                    error.issues,
                    project=service.context,
                ) from error
    except PrismClientError as error:
        raise CliFailure(
            _client_exit(error),
            error.issues,
            project=local_context,
        ) from error


def require_entity_type(value: str, *, named: bool = False) -> str:
    """Validate one public entity discriminator."""

    normalized = value.casefold()
    allowed = _NAMED_ENTITY_TYPES if named else _ENTITY_TYPES
    if normalized not in allowed:
        choices = ", ".join(sorted(allowed))
        raise CliFailure(
            CliExit.USAGE,
            ApiIssue(
                code="invalid_entity_type",
                path="/entity_type",
                message=f"Entity type must be one of: {choices}",
            ),
        )
    return normalized


def list_entities(client: PrismClient, project_id: UUID, entity_type: str) -> list[Any]:
    """Dispatch an entity-list request while preserving typed client responses."""

    dispatch: dict[str, Callable[[UUID], list[Any]]] = {
        "track": cast(Callable[[UUID], list[Any]], client.list_tracks),
        "scene": cast(Callable[[UUID], list[Any]], client.list_scenes),
        "clip": cast(Callable[[UUID], list[Any]], client.list_clips),
        "asset": cast(Callable[[UUID], list[Any]], client.list_assets),
        "slot": cast(Callable[[UUID], list[Any]], client.list_slots),
    }
    return dispatch[require_entity_type(entity_type)](project_id)


def resolve_selector(
    client: PrismClient,
    project_id: UUID,
    entity_type: str,
    selector: str,
) -> UUID:
    """Resolve a UUID or a unique, exact case-insensitive entity name."""

    normalized_type = require_entity_type(entity_type, named=True)
    try:
        candidate = UUID(selector)
    except ValueError:
        return client.resolve_name(project_id, normalized_type, selector)
    if not any(item.id == candidate for item in list_entities(client, project_id, normalized_type)):
        raise CliFailure(
            CliExit.VALIDATION,
            ApiIssue(
                code=f"{normalized_type}_not_found",
                path=f"/{normalized_type}",
                message=f"{normalized_type.title()} does not exist: {candidate}",
            ),
        )
    return candidate


def read_json(path: Path | str) -> Any:
    """Read one bounded UTF-8 JSON document."""

    try:
        source = Path(path).resolve(strict=True)
    except OSError as error:
        raise CliFailure(
            CliExit.USAGE,
            ApiIssue(code="input_not_found", path=str(path), message=str(error)),
        ) from error
    size = source.stat().st_size
    if size > MAX_INPUT_BYTES:
        raise CliFailure(
            CliExit.USAGE,
            ApiIssue(
                code="input_too_large",
                path=str(source),
                message=f"JSON input exceeds {MAX_INPUT_BYTES} bytes",
            ),
        )
    return json.loads(source.read_text(encoding="utf-8"))


def transaction_request(
    document: Any,
    *,
    current_revision: int,
    base_revision: int | None,
    idempotency_key: str | None,
    allow_runtime_reset: bool,
) -> TransactionRequest:
    """Accept either a full transaction object or a bare operation array."""

    if isinstance(document, list):
        payload: dict[str, Any] = {
            "base_revision": current_revision if base_revision is None else base_revision,
            "operations": document,
            "allow_runtime_reset": allow_runtime_reset,
        }
        if idempotency_key is not None:
            payload["idempotency_key"] = idempotency_key
    elif isinstance(document, dict):
        payload = dict(document)
        if base_revision is not None:
            payload["base_revision"] = base_revision
        elif "base_revision" not in payload:
            payload["base_revision"] = current_revision
        if idempotency_key is not None:
            payload["idempotency_key"] = idempotency_key
        if allow_runtime_reset:
            payload["allow_runtime_reset"] = True
    else:
        raise CliFailure(
            CliExit.USAGE,
            ApiIssue(
                code="invalid_transaction_file",
                message="Transaction file must contain an object or an operations array",
            ),
        )
    return TransactionRequest.model_validate(payload)


def wait_for_job(
    client: PrismClient,
    project_id: UUID,
    job_id: UUID,
    *,
    timeout: float,
    on_update: Callable[[BackgroundJob], None] | None = None,
) -> BackgroundJob:
    """Poll a job with a CLI deadline and optional human progress callback."""

    deadline = time.monotonic() + timeout
    last: tuple[str, float] | None = None
    while True:
        job = client.get_job(project_id, job_id)
        marker = (job.state, job.progress)
        if on_update is not None and marker != last:
            on_update(job)
        last = marker
        if job.state in {"completed", "failed", "cancelled"}:
            return job
        if time.monotonic() >= deadline:
            raise CliFailure(
                CliExit.JOB,
                ApiIssue(
                    code="job_timeout",
                    message=f"Job did not finish before the {timeout:g}s timeout: {job_id}",
                ),
            )
        time.sleep(0.1)


def require_successful_job(job: BackgroundJob, project: ProjectContext) -> BackgroundJob:
    """Map failed or cancelled terminal jobs to the stable job exit class."""

    if job.state == "completed":
        return job
    issue = job.error or ApiIssue(
        code=f"job_{job.state}",
        message=f"Job ended in state {job.state}: {job.job_id}",
    )
    raise CliFailure(
        CliExit.JOB,
        issue,
        project=project,
        data=job.model_dump(mode="json"),
    )


def failed_transaction(
    result: BaseModel,
    issues: list[ApiIssue],
    project: ProjectContext,
) -> CliFailure:
    """Classify rejected transactions without losing their preview details."""

    conflict_codes = {
        "stale_revision",
        "external_project_change",
        "project_locked",
        "idempotency_conflict",
    }
    exit_code = (
        CliExit.CONFLICT
        if any(issue.code in conflict_codes for issue in issues)
        else CliExit.VALIDATION
    )
    return CliFailure(
        exit_code,
        issues,
        project=project,
        data=result.model_dump(mode="json"),
    )


def json_line(value: Any) -> str:
    """Serialize one stable compact JSON line."""

    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _read_working_manifest(path: Path) -> Project:
    manifest = path / "project.json"
    try:
        return Project.model_validate_json(manifest.read_text(encoding="utf-8"))
    except OSError as error:
        raise WorkingProjectError(f"Could not read working project manifest: {manifest}") from error


def _is_loopback(host: str) -> bool:
    if host.casefold() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _client_exit(error: PrismClientError) -> CliExit:
    codes = {issue.code for issue in error.issues}
    return _status_exit(error.status_code, codes)


def _status_exit(status_code: int, codes: set[str]) -> CliExit:
    if status_code == 409 or codes.intersection(
        {"stale_revision", "external_project_change", "project_locked", "project_mismatch"}
    ):
        return CliExit.CONFLICT
    if codes.intersection({"audio_error", "audio_device_unavailable", "audio_faulted"}):
        return CliExit.AUDIO
    if codes.intersection({"job_timeout", "job_failed", "job_cancelled", "job_queue_full"}):
        return CliExit.JOB
    if status_code == 0 or status_code >= 500:
        return CliExit.SERVICE
    if status_code in {400, 404, 413, 422, 429}:
        return CliExit.VALIDATION
    return CliExit.SERVICE


def _project_issues(error: Exception) -> list[ApiIssue]:
    raw = getattr(error, "issues", ())
    if raw:
        return [ApiIssue(code=item.code, path=item.path, message=item.message) for item in raw]
    return [ApiIssue(code="invalid_project", message=str(error))]


def _emit_success(command: str, as_json: bool, dry_run: bool, result: CommandResult) -> None:
    envelope = CliEnvelope(
        ok=True,
        command=command,
        project=result.project,
        dry_run=dry_run,
        data=result.data,
        warnings=result.warnings,
    )
    if as_json:
        typer.echo(json_line(envelope.model_dump(mode="json")))
        return
    if result.human:
        for line in result.human:
            typer.echo(line)
    elif result.data is not None:
        typer.echo(
            json.dumps(
                result.data,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
                default=str,
            )
        )
    for warning in result.warnings:
        typer.echo(f"warning: {warning.code}: {warning.message}", err=True)


def _emit_failure(command: str, as_json: bool, dry_run: bool, error: CliFailure) -> None:
    envelope = CliEnvelope(
        ok=False,
        command=command,
        project=error.project,
        dry_run=dry_run,
        data=error.data,
        errors=error.issues,
    )
    if as_json:
        typer.echo(json_line(envelope.model_dump(mode="json")))
    else:
        for issue in error.issues:
            location = f" {issue.path}" if issue.path else ""
            typer.echo(f"{issue.code}{location}: {issue.message}", err=True)
    raise typer.Exit(code=int(error.exit_code))
