from __future__ import annotations

import time
from pathlib import Path

import pytest

from prism.application import (
    ApplicationError,
    ApplicationService,
    ExportJobRequest,
    RenderJobRequest,
    TransactionRequest,
)
from prism.audio import FakeAudioBackend
from prism.rendering import RenderCancelledError, RenderOutputError

from ._helpers import make_archive_fixture


def _wait(service: ApplicationService, job_id, timeout: float = 3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = service.get_job(job_id)
        if job.state in {"completed", "failed", "cancelled"}:
            return job
        time.sleep(0.01)
    raise AssertionError("job did not finish")


def test_render_and_export_jobs_are_revision_bound_and_hashed(tmp_path: Path) -> None:
    project_path, project, _, scene, _ = make_archive_fixture(tmp_path)
    service = ApplicationService(project_path, backend_factory=FakeAudioBackend)
    try:
        render_job = service.submit_render(
            RenderJobRequest(
                output_path="mix.wav",
                seconds=1.0,
                commands=[
                    {
                        "frame": 0,
                        "operation": "launch_scene",
                        "scene_id": scene.id,
                    }
                ],
            )
        )
        rendered = _wait(service, render_job.job_id)

        first = _wait(
            service,
            service.submit_export(ExportJobRequest(output_path="first.prism")).job_id,
        )
        second = _wait(
            service,
            service.submit_export(ExportJobRequest(output_path="second.prism")).job_id,
        )

        assert rendered.state == "completed"
        assert rendered.revision == project.revision.number
        assert rendered.output_sha256 is not None
        assert Path(rendered.output_path or "").is_file()
        assert first.output_sha256 == second.output_sha256
        assert Path(first.output_path or "").read_bytes() == Path(
            second.output_path or ""
        ).read_bytes()
    finally:
        service.close()

    reopened = ApplicationService(project_path, backend_factory=FakeAudioBackend)
    try:
        retained = {job.job_id: job for job in reopened.list_jobs()}
        assert render_job.job_id in retained
        assert retained[render_job.job_id].output_sha256 == rendered.output_sha256
    finally:
        reopened.close()


def test_render_job_can_be_cancelled_without_blocking_project_edits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_path, project, _, _, _ = make_archive_fixture(tmp_path)

    def slow_render(*args, cancel_event, progress, **kwargs):
        del args, kwargs
        while not cancel_event.wait(0.01):
            progress(0.25)
        raise RenderCancelledError("cancelled")

    monkeypatch.setattr("prism.application.jobs.render_snapshot", slow_render)
    service = ApplicationService(project_path, backend_factory=FakeAudioBackend)
    try:
        job = service.submit_render(RenderJobRequest(output_path="slow.wav", seconds=2.0))
        committed = service.commit_transaction(
            TransactionRequest(
                base_revision=project.revision.number,
                operations=[{"op": "project.rename", "name": "Still responsive"}],
            )
        )
        cancelled = service.cancel_job(job.job_id)
        terminal = _wait(service, job.job_id)

        assert committed.ok
        assert cancelled.state in {"queued", "running", "cancelled"}
        assert terminal.state == "cancelled"
        assert not (service.working_path / "exports" / "slow.wav").exists()
    finally:
        service.close()


def test_job_queue_is_bounded_and_failures_are_structured(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_path, _, _, _, _ = make_archive_fixture(tmp_path)

    def slow_render(*args, cancel_event, progress, **kwargs):
        del args, progress, kwargs
        while not cancel_event.wait(0.01):
            pass
        raise RenderCancelledError("cancelled")

    monkeypatch.setattr("prism.application.jobs.render_snapshot", slow_render)
    service = ApplicationService(project_path, backend_factory=FakeAudioBackend)
    try:
        jobs = [
            service.submit_render(
                RenderJobRequest(output_path=f"queued-{index}.wav", seconds=1.0)
            )
            for index in range(9)
        ]
        with pytest.raises(ApplicationError) as full:
            service.submit_render(RenderJobRequest(output_path="full.wav", seconds=1.0))
        assert full.value.code == "job_queue_full"
        for job in jobs:
            service.cancel_job(job.job_id)
        assert all(_wait(service, job.job_id).state == "cancelled" for job in jobs)
    finally:
        service.close()

    def failed_render(*args, **kwargs):
        del args, kwargs
        raise RenderOutputError("deliberate failure")

    monkeypatch.setattr("prism.application.jobs.render_snapshot", failed_render)
    service = ApplicationService(project_path, backend_factory=FakeAudioBackend)
    try:
        failed = _wait(
            service,
            service.submit_render(RenderJobRequest(output_path="failed.wav", seconds=1.0)).job_id,
        )
        assert failed.state == "failed"
        assert failed.error is not None
        assert failed.error.code == "job_failed"
    finally:
        service.close()
