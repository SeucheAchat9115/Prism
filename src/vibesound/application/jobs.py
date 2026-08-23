"""Bounded revision-snapshot render and portable-export jobs."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from threading import BoundedSemaphore, Event, RLock
from typing import Literal
from uuid import UUID, uuid4

from vibesound.application.errors import ApplicationError
from vibesound.application.types import (
    ApiIssue,
    BackgroundJob,
    ExportJobRequest,
    JobPreview,
    RenderJobRequest,
)
from vibesound.project import ProjectRepository, RepositorySnapshot, WorkingProjectError
from vibesound.rendering import RenderCancelledError, RenderError, render_snapshot

JobPublisher = Callable[[str, dict[str, object]], None]
_RETENTION_SECONDS = 7 * 24 * 3600
_MAX_RETAINED_JOBS = 1000
_MAX_PROGRESS_HZ = 10.0


class RenderJobService:
    """Run one render/export at a time with eight additional queued jobs."""

    def __init__(
        self,
        repository: ProjectRepository,
        *,
        publisher: JobPublisher | None = None,
    ) -> None:
        self._repository = repository
        self._publisher = publisher or (lambda _event, _payload: None)
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="vibesound-job")
        self._capacity = BoundedSemaphore(9)
        self._lock = RLock()
        self._jobs: dict[UUID, BackgroundJob] = {}
        self._futures: dict[UUID, Future[None]] = {}
        self._cancel: dict[UUID, Event] = {}
        self._idempotency: dict[str, tuple[str, UUID]] = {}
        self._closed = False
        self._load_retained_jobs()

    def submit_render(self, request: RenderJobRequest) -> BackgroundJob:
        digest = _digest(request.model_dump(mode="json"))
        replay = self._idempotent_job(request.idempotency_key, digest)
        if replay is not None:
            return replay
        snapshot = self._repository.snapshot()
        output = self._repository.resolve_output(request.output_path)
        job = self._new_job(
            "render",
            snapshot.project.project_id,
            snapshot.project.revision.number,
            request.model_dump(mode="json"),
            str(output),
        )
        self._remember_idempotency(request.idempotency_key, digest, job.job_id)
        self._enqueue(
            job,
            lambda cancel: self._run_render(job.job_id, snapshot, output, request, cancel),
        )
        return self.get(job.job_id)

    def preview_render(self, request: RenderJobRequest) -> JobPreview:
        """Validate a render job target without reserving queue capacity."""

        return self._preview("render", request.output_path, request.model_dump(mode="json"))

    def submit_export(self, request: ExportJobRequest) -> BackgroundJob:
        digest = _digest(request.model_dump(mode="json"))
        replay = self._idempotent_job(request.idempotency_key, digest)
        if replay is not None:
            return replay
        snapshot = self._repository.snapshot()
        output = self._repository.resolve_output(request.output_path)
        job = self._new_job(
            "export",
            snapshot.project.project_id,
            snapshot.project.revision.number,
            request.model_dump(mode="json"),
            str(output),
        )
        self._remember_idempotency(request.idempotency_key, digest, job.job_id)
        self._enqueue(
            job,
            lambda cancel: self._run_export(job.job_id, snapshot, request, cancel),
        )
        return self.get(job.job_id)

    def preview_export(self, request: ExportJobRequest) -> JobPreview:
        """Validate an export job target without creating output or metadata."""

        return self._preview("export", request.output_path, request.model_dump(mode="json"))

    def get(self, job_id: UUID) -> BackgroundJob:
        with self._lock:
            try:
                return self._jobs[job_id].model_copy(deep=True)
            except KeyError as error:
                raise ApplicationError(
                    f"Background job does not exist: {job_id}",
                    code="job_not_found",
                    status_code=404,
                ) from error

    def list(self) -> list[BackgroundJob]:
        with self._lock:
            return [
                self._jobs[job_id].model_copy(deep=True)
                for job_id in sorted(
                    self._jobs,
                    key=lambda value: self._jobs[value].created_at,
                    reverse=True,
                )
            ]

    def cancel(self, job_id: UUID) -> BackgroundJob:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise ApplicationError(
                    f"Background job does not exist: {job_id}",
                    code="job_not_found",
                    status_code=404,
                )
            if job.state in {"completed", "failed", "cancelled"}:
                return job.model_copy(deep=True)
            self._cancel[job_id].set()
            future = self._futures.get(job_id)
            if job.state == "queued" and future is not None and future.cancel():
                self._finish_cancelled(job_id)
                self._capacity.release()
            return self._jobs[job_id].model_copy(deep=True)

    def wait(self, job_id: UUID, timeout: float | None = None) -> BackgroundJob:
        with self._lock:
            future = self._futures.get(job_id)
        if future is None:
            return self.get(job_id)
        try:
            future.result(timeout=timeout)
        except TimeoutError as error:
            raise ApplicationError(
                "Background job did not finish before the timeout",
                code="job_timeout",
                status_code=503,
            ) from error
        return self.get(job_id)

    def close(self, timeout: float = 5.0) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            for cancel in self._cancel.values():
                cancel.set()
            for job_id, job in self._jobs.items():
                future = self._futures.get(job_id)
                if (
                    job.state == "queued"
                    and future is not None
                    and future.cancel()
                ):
                    self._finish_cancelled(job_id)
                    self._capacity.release()
            futures = tuple(self._futures.values())
        deadline = time.monotonic() + timeout
        for future in futures:
            if future.done():
                continue
            try:
                future.result(timeout=max(0.0, deadline - time.monotonic()))
            except Exception:
                break
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _new_job(
        self,
        kind: Literal["render", "export"],
        project_id: UUID,
        revision: int,
        request: dict[str, object],
        output_path: str,
    ) -> BackgroundJob:
        with self._lock:
            if self._closed:
                raise ApplicationError(
                    "Background job service is closed",
                    code="service_closed",
                    status_code=409,
                )
            self._cleanup_unlocked()
            if not self._capacity.acquire(blocking=False):
                raise ApplicationError(
                    "The render queue is full",
                    code="job_queue_full",
                    status_code=429,
                )
            job = BackgroundJob(
                job_id=uuid4(),
                kind=kind,
                state="queued",
                project_id=project_id,
                revision=revision,
                request=request,
                output_path=output_path,
                created_at=time.time(),
            )
            self._jobs[job.job_id] = job
            self._cancel[job.job_id] = Event()
            self._persist_unlocked(job)
            self._publish(job, "job.queued")
            return job

    def _preview(
        self,
        kind: Literal["render", "export"],
        output_path: str,
        request: dict[str, object],
    ) -> JobPreview:
        snapshot = self._repository.snapshot()
        output = self._repository.resolve_output(output_path)
        return JobPreview(
            kind=kind,
            project_id=snapshot.project.project_id,
            revision=snapshot.project.revision.number,
            output_path=str(output),
            request=request,
        )

    def _enqueue(
        self,
        job: BackgroundJob,
        operation: Callable[[Event], None],
    ) -> None:
        try:
            future = self._executor.submit(self._run, job.job_id, operation)
        except Exception:
            self._capacity.release()
            raise
        with self._lock:
            self._futures[job.job_id] = future

    def _run(self, job_id: UUID, operation: Callable[[Event], None]) -> None:
        try:
            with self._lock:
                cancel = self._cancel[job_id]
                if cancel.is_set():
                    self._finish_cancelled(job_id)
                    return
                job = self._jobs[job_id]
                job.state = "running"
                job.started_at = time.time()
                self._persist_unlocked(job)
                self._publish(job, "job.started")
            operation(cancel)
        except RenderCancelledError:
            self._finish_cancelled(job_id)
        except (RenderError, WorkingProjectError, OSError, ValueError) as error:
            with self._lock:
                job = self._jobs[job_id]
                job.state = "failed"
                job.finished_at = time.time()
                job.error = ApiIssue(code="job_failed", message=str(error))
                self._persist_unlocked(job)
                self._publish(job, "job.failed")
        except Exception as error:  # pragma: no cover - defensive worker boundary
            with self._lock:
                job = self._jobs[job_id]
                job.state = "failed"
                job.finished_at = time.time()
                job.error = ApiIssue(code="job_internal_error", message=str(error))
                self._persist_unlocked(job)
                self._publish(job, "job.failed")
        finally:
            self._capacity.release()

    def _run_render(
        self,
        job_id: UUID,
        snapshot: RepositorySnapshot,
        output: Path,
        request: RenderJobRequest,
        cancel: Event,
    ) -> None:
        last_published = 0.0

        def progress(value: float) -> None:
            nonlocal last_published
            now = time.monotonic()
            if value < 1.0 and now - last_published < 1.0 / _MAX_PROGRESS_HZ:
                return
            last_published = now
            with self._lock:
                job = self._jobs[job_id]
                job.progress = value
                self._persist_unlocked(job)
                self._publish(job, "job.progress")

        metadata = render_snapshot(
            snapshot,
            output,
            request.to_domain(),
            cancel_event=cancel,
            progress=progress,
        )
        self._finish_completed(job_id, metadata.output_path, _hash_file(metadata.output_path))

    def _run_export(
        self,
        job_id: UUID,
        snapshot: RepositorySnapshot,
        request: ExportJobRequest,
        cancel: Event,
    ) -> None:
        if cancel.is_set():
            raise RenderCancelledError("Export job was cancelled")
        output, digest = self._repository.export_snapshot(
            snapshot,
            request.output_path,
        )
        self._finish_completed(job_id, output, digest)

    def _finish_completed(self, job_id: UUID, output: Path, digest: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.state = "completed"
            job.progress = 1.0
            job.output_path = str(output)
            job.output_sha256 = digest
            job.finished_at = time.time()
            self._persist_unlocked(job)
            self._publish(job, "job.completed")

    def _finish_cancelled(self, job_id: UUID) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.state = "cancelled"
            job.finished_at = time.time()
            self._persist_unlocked(job)
            self._publish(job, "job.cancelled")

    def _persist_unlocked(self, job: BackgroundJob) -> None:
        self._repository.write_job_metadata(
            job.job_id,
            job.model_dump(mode="json"),
        )

    def _publish(self, job: BackgroundJob, event_type: str) -> None:
        self._publisher(
            event_type,
            {
                "job_id": str(job.job_id),
                "kind": job.kind,
                "state": job.state,
                "progress": job.progress,
                "revision": job.revision,
                "output_path": job.output_path,
                "output_sha256": job.output_sha256,
            },
        )

    def _cleanup_unlocked(self) -> None:
        terminal = [
            job
            for job in self._jobs.values()
            if job.state in {"completed", "failed", "cancelled"}
        ]
        terminal.sort(key=lambda job: job.finished_at or job.created_at, reverse=True)
        cutoff = time.time() - _RETENTION_SECONDS
        remove = {
            job.job_id
            for index, job in enumerate(terminal)
            if index >= _MAX_RETAINED_JOBS or (job.finished_at or job.created_at) < cutoff
        }
        for job_id in remove:
            self._jobs.pop(job_id, None)
            self._futures.pop(job_id, None)
            self._cancel.pop(job_id, None)
            self._repository.delete_job_metadata(job_id)

    def _load_retained_jobs(self) -> None:
        now = time.time()
        for document in self._repository.read_job_metadata():
            job = BackgroundJob.model_validate(document)
            if job.state in {"queued", "running"}:
                job.state = "failed"
                job.finished_at = now
                job.error = ApiIssue(
                    code="job_interrupted",
                    message="The service stopped before this job reached a terminal state.",
                )
                self._repository.write_job_metadata(
                    job.job_id,
                    job.model_dump(mode="json"),
                )
            self._jobs[job.job_id] = job
        with self._lock:
            self._cleanup_unlocked()

    def _idempotent_job(self, key: str | None, digest: str) -> BackgroundJob | None:
        if key is None:
            return None
        with self._lock:
            existing = self._idempotency.get(key)
            if existing is None:
                return None
            existing_digest, job_id = existing
            if existing_digest != digest:
                raise ApplicationError(
                    "The idempotency key was already used for another job request.",
                    code="idempotency_conflict",
                    status_code=409,
                )
            return self._jobs[job_id].model_copy(deep=True)

    def _remember_idempotency(self, key: str | None, digest: str, job_id: UUID) -> None:
        if key is not None:
            with self._lock:
                self._idempotency[key] = (digest, job_id)


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _digest(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
