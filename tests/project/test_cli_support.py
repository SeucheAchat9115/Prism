from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest
import typer
from pydantic import BaseModel

from vibesound.api import VibeSoundClientError
from vibesound.application import ApiIssue, BackgroundJob, TransactionResult
from vibesound.application.errors import ApplicationError
from vibesound.command_line import support
from vibesound.command_line.support import (
    CliExit,
    CliFailure,
    CommandResult,
    ProjectContext,
    emit_stream_failure,
    failed_transaction,
    read_json,
    require_entity_type,
    require_successful_job,
    run_command,
    transaction_request,
    validate_service_url,
    wait_for_job,
)
from vibesound.project import InvalidArchiveError, ProjectLockedError, WorkingProjectError


@pytest.mark.parametrize(
    ("value", "code"),
    (
        ("http://localhost:bad", "invalid_service_url"),
        ("localhost:8765", "invalid_service_url"),
        ("http://user@localhost", "invalid_service_url"),
        ("http://localhost/api", "invalid_service_url"),
        ("http://example.com", "non_loopback_service"),
    ),
)
def test_service_url_policy_rejects_unsafe_values(value: str, code: str) -> None:
    with pytest.raises(CliFailure) as failure:
        validate_service_url(value)

    assert failure.value.exit_code == CliExit.USAGE
    assert failure.value.issues[0].code == code


def test_service_url_policy_normalizes_ipv4_ipv6_and_localhost() -> None:
    assert validate_service_url("http://127.0.0.1:9000/") == "http://127.0.0.1:9000"
    assert validate_service_url("https://[::1]:9443") == "https://[::1]:9443"
    assert validate_service_url("http://LOCALHOST") == "http://localhost"


def test_bounded_json_and_entity_validation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    value = tmp_path / "value.json"
    value.write_text("[]", encoding="utf-8")
    assert read_json(value) == []

    with pytest.raises(CliFailure) as missing:
        read_json(tmp_path / "missing.json")
    assert missing.value.issues[0].code == "input_not_found"

    monkeypatch.setattr(support, "MAX_INPUT_BYTES", 1)
    with pytest.raises(CliFailure) as oversized:
        read_json(value)
    assert oversized.value.issues[0].code == "input_too_large"

    assert require_entity_type("TRACK") == "track"
    with pytest.raises(CliFailure) as invalid_entity:
        require_entity_type("job", named=True)
    assert invalid_entity.value.exit_code == CliExit.USAGE


def test_transaction_file_forms_apply_explicit_overrides() -> None:
    from_array = transaction_request(
        [{"op": "project.rename", "name": "Array"}],
        current_revision=3,
        base_revision=None,
        idempotency_key="array-key",
        allow_runtime_reset=True,
    )
    from_object = transaction_request(
        {"operations": [{"op": "project.rename", "name": "Object"}]},
        current_revision=4,
        base_revision=2,
        idempotency_key="object-key",
        allow_runtime_reset=True,
    )
    preserved = transaction_request(
        {
            "base_revision": 7,
            "operations": [{"op": "project.rename", "name": "Preserved"}],
        },
        current_revision=9,
        base_revision=None,
        idempotency_key=None,
        allow_runtime_reset=False,
    )

    assert from_array.base_revision == 3
    assert from_array.idempotency_key == "array-key"
    assert from_array.allow_runtime_reset
    assert from_object.base_revision == 2
    assert from_object.idempotency_key == "object-key"
    assert preserved.base_revision == 7
    with pytest.raises(CliFailure):
        transaction_request(
            "not a request",
            current_revision=0,
            base_revision=None,
            idempotency_key=None,
            allow_runtime_reset=False,
        )


class _JobClient:
    def __init__(self, jobs: list[BackgroundJob]) -> None:
        self.jobs = jobs

    def get_job(self, project_id: UUID, job_id: UUID) -> BackgroundJob:
        del project_id, job_id
        return self.jobs.pop(0) if len(self.jobs) > 1 else self.jobs[0]


def _job(state: str, *, error: ApiIssue | None = None) -> BackgroundJob:
    return BackgroundJob.model_validate(
        {
            "job_id": uuid4(),
            "kind": "render",
            "state": state,
            "project_id": uuid4(),
            "revision": 1,
            "progress": 1.0 if state == "completed" else 0.25,
            "request": {"seconds": 1.0},
            "created_at": 1.0,
            "error": None if error is None else error.model_dump(mode="json"),
        }
    )


def test_job_wait_and_terminal_failure_classification(monkeypatch: pytest.MonkeyPatch) -> None:
    queued = _job("queued")
    completed = queued.model_copy(update={"state": "completed", "progress": 1.0})
    updates: list[str] = []
    monkeypatch.setattr(support.time, "sleep", lambda _seconds: None)

    terminal = wait_for_job(
        _JobClient([queued, completed]),  # type: ignore[arg-type]
        queued.project_id,
        queued.job_id,
        timeout=1.0,
        on_update=lambda job: updates.append(job.state),
    )
    context = ProjectContext(path="project.vibesound-work", id=queued.project_id, revision=1)

    assert terminal.state == "completed"
    assert updates == ["queued", "completed"]
    assert require_successful_job(terminal, context) is terminal

    failed = _job("failed", error=ApiIssue(code="job_failed", message="failed"))
    with pytest.raises(CliFailure) as failure:
        require_successful_job(failed, context)
    assert failure.value.exit_code == CliExit.JOB

    with pytest.raises(CliFailure) as timeout:
        wait_for_job(
            _JobClient([queued]),  # type: ignore[arg-type]
            queued.project_id,
            queued.job_id,
            timeout=0.0,
        )
    assert timeout.value.issues[0].code == "job_timeout"


def test_transaction_and_stream_failures_preserve_stable_exit_classes(capsys) -> None:
    context = ProjectContext(path="project.vibesound-work", id=uuid4(), revision=2)
    result = TransactionResult(
        ok=False,
        committed=False,
        base_revision=1,
        before_revision=2,
        after_revision=2,
        current_revision=2,
    )
    conflict = failed_transaction(
        result,
        [ApiIssue(code="stale_revision", message="stale")],
        context,
    )
    rejected = failed_transaction(
        result,
        [ApiIssue(code="invalid_value", message="invalid")],
        context,
    )
    assert conflict.exit_code == CliExit.CONFLICT
    assert rejected.exit_code == CliExit.VALIDATION

    for error, code in (
        (TimeoutError(), CliExit.JOB),
        (KeyboardInterrupt(), CliExit.INTERRUPTED),
        (RuntimeError("closed"), CliExit.SERVICE),
        (
            VibeSoundClientError(
                503,
                [ApiIssue(code="audio_error", message="audio")],
            ),
            CliExit.AUDIO,
        ),
    ):
        with pytest.raises(typer.Exit) as emitted:
            emit_stream_failure("events watch", True, error)
        assert emitted.value.exit_code == int(code)
    assert "cli_schema_version" in capsys.readouterr().out


class _StrictInput(BaseModel):
    value: int


@pytest.mark.parametrize(
    ("error", "exit_code"),
    (
        (ApplicationError("bad", code="bad", status_code=422), CliExit.VALIDATION),
        (ProjectLockedError("locked"), CliExit.CONFLICT),
        (InvalidArchiveError("invalid"), CliExit.VALIDATION),
        (WorkingProjectError("write failed"), CliExit.IO),
    ),
)
def test_command_boundary_normalizes_known_failures(error: Exception, exit_code: CliExit) -> None:
    def fail() -> CommandResult:
        raise error

    with pytest.raises(typer.Exit) as emitted:
        run_command("test", as_json=True, action=fail)
    assert emitted.value.exit_code == int(exit_code)


def test_command_boundary_normalizes_pydantic_and_json_errors() -> None:
    def invalid_model() -> CommandResult:
        _StrictInput.model_validate({"value": "not-an-integer"})
        raise AssertionError

    def invalid_json() -> CommandResult:
        json.loads("{")
        raise AssertionError

    for action in (invalid_model, invalid_json):
        with pytest.raises(typer.Exit) as emitted:
            run_command("test", as_json=True, action=action)
        assert emitted.value.exit_code == int(CliExit.USAGE)
