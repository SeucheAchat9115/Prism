"""Composition root for repository, commands, runtime, jobs, and API events."""

from __future__ import annotations

from pathlib import Path
from threading import RLock
from typing import BinaryIO
from uuid import UUID

import soundfile as sf

from vibesound.application.commands import ProjectCommandService
from vibesound.application.errors import ApplicationError
from vibesound.application.events import EventHub, EventSubscription
from vibesound.application.jobs import RenderJobService
from vibesound.application.runtime import AudioRuntimeCoordinator, BackendFactory
from vibesound.application.types import (
    ApiIssue,
    ApplicationSnapshot,
    AudioDeviceModel,
    AudioSnapshotModel,
    BackgroundJob,
    ClipLaunchRequest,
    ClipStopRequest,
    EngineSnapshotModel,
    EventEnvelope,
    ExportJobRequest,
    RenderJobRequest,
    RuntimeImpact,
    TransactionRequest,
    TransactionResult,
    TransportRequest,
)
from vibesound.audio import AudioBackendError, OfflineRenderBackend
from vibesound.engine import EngineError
from vibesound.engine.types import ScheduledAction
from vibesound.project import (
    LayeredValidationReport,
    ProjectArchiveError,
    ProjectRepository,
    StagedAudioUpload,
    WorkingProjectError,
)
from vibesound.project.models import Project
from vibesound.rendering import RenderError
from vibesound.rendering.types import RenderMetadata


class ApplicationService:
    """Own the single-writer project process and all application boundaries."""

    def __init__(
        self,
        project_path: Path | str,
        *,
        backend_factory: BackendFactory | None = None,
        renderer: OfflineRenderBackend | None = None,
    ) -> None:
        del renderer  # synchronous rendering is now a compatibility adapter over jobs
        self._project_path = Path(project_path)
        self._lock = RLock()
        self._events = EventHub(max_subscribers=32, queue_capacity=256)
        self._closed = False
        try:
            self._repository = ProjectRepository.open(self._project_path)
            self._project = self._repository.get_project()
            self._commands = ProjectCommandService(self._repository)
            self._runtime = AudioRuntimeCoordinator(
                self._repository,
                backend_factory=backend_factory,
                publisher=self._publish,
            )
            self._jobs = RenderJobService(self._repository, publisher=self._publish)
        except (ProjectArchiveError, WorkingProjectError, RenderError, ValueError) as error:
            repository = getattr(self, "_repository", None)
            if repository is not None:
                repository.close()
            raise ApplicationError(
                f"Could not open project: {error}",
                code="invalid_project",
                status_code=422,
            ) from error

    @property
    def project_path(self) -> Path:
        return self._project_path

    @property
    def working_path(self) -> Path:
        return self._repository.working_path

    @property
    def project_id(self) -> UUID:
        with self._lock:
            self._require_open()
            return self._project.project_id

    def get_project(self) -> Project:
        with self._lock:
            self._require_open()
            return self._project.model_copy(deep=True)

    def validate(self) -> LayeredValidationReport:
        return self._repository.validation_report()

    def get_snapshot(self) -> ApplicationSnapshot:
        with self._lock:
            self._require_open()
            backend = self._runtime.snapshot()
            return ApplicationSnapshot(
                project_id=self._project.project_id,
                revision=self._project.revision.number,
                engine=EngineSnapshotModel.from_snapshot(backend.engine_snapshot),
                audio=AudioSnapshotModel.from_snapshot(backend),
            )

    def subscribe(self) -> EventSubscription:
        with self._lock:
            self._require_open()
            try:
                return self._events.subscribe()
            except RuntimeError as error:
                raise ApplicationError(
                    "The event subscriber limit has been reached",
                    code="subscriber_limit",
                    status_code=429,
                ) from error

    def preview_transaction(self, request: TransactionRequest) -> TransactionResult:
        with self._lock:
            self._require_open()
            result = self._commands.preview(request)
            self._refine_runtime_impact(result)
            return result

    def commit_transaction(self, request: TransactionRequest) -> TransactionResult:
        with self._lock:
            self._require_open()
            current_revision = self._project.revision.number
            if request.idempotency_key is not None and request.base_revision != current_revision:
                replay, _ = self._commands.commit(request)
                return replay
            preview = self._commands.preview(request)
            self._refine_runtime_impact(preview)
            if not preview.ok:
                return preview
            if preview.runtime_reset_required and not request.allow_runtime_reset:
                preview.ok = False
                preview.errors.append(
                    ApiIssue(
                        code="runtime_reset_required",
                        message=(
                            "This transaction requires a runtime reset; retry with "
                            "allow_runtime_reset=true after previewing its impact."
                        ),
                    )
                )
                return preview
            result, committed = self._commands.commit(request)
            if not result.ok or committed is None or result.idempotent_replay:
                if any(issue.code == "external_project_change" for issue in result.errors):
                    self._publish(
                        "project.external_change",
                        {"source": str(self._repository.source_archive or self.working_path)},
                    )
                return result
            result.runtime_impact = preview.runtime_impact
            result.runtime_reset_required = preview.runtime_reset_required
            self._project = committed
            try:
                result.runtime_reset_performed = self._runtime.apply_project(
                    committed,
                    result.runtime_impact,
                )
            except (AudioBackendError, EngineError, RenderError, OSError, ValueError) as error:
                result.warnings.append(
                    ApiIssue(
                        code="runtime_refresh_failed",
                        message=f"Project committed but runtime refresh failed: {error}",
                    )
                )
                self._publish(
                    "audio.error",
                    {"code": "runtime_refresh_failed", "message": str(error)},
                )
            self._publish(
                "project.changed",
                {
                    "changed_paths": result.changed_paths,
                    "before_revision": result.before_revision,
                    "after_revision": result.after_revision,
                    "runtime_impact": result.runtime_impact.value,
                    "runtime_reset_performed": result.runtime_reset_performed,
                },
            )
            return result

    def transport(self, request: TransportRequest) -> ApplicationSnapshot:
        with self._lock:
            self._require_open()
            try:
                self._runtime.transport(request.operation)
            except (AudioBackendError, EngineError) as error:
                self._publish("audio.error", {"code": "transport_error", "message": str(error)})
                raise ApplicationError(str(error), code="audio_error", status_code=503) from error
            snapshot = self.get_snapshot()
            self._publish(
                "transport.changed",
                {
                    "operation": request.operation,
                    "state": snapshot.audio.state,
                    "position_frame": snapshot.engine.position_frame,
                    "audible_position_frame": snapshot.audio.audible_position_frame,
                },
            )
            return snapshot

    def launch_clip(self, clip_id: UUID, request: ClipLaunchRequest) -> ScheduledAction:
        with self._lock:
            self._require_open()
            self._require_clip(clip_id)
            self._require_track(request.track_id)
            self._require_scene(request.scene_id)
            if not any(
                slot.track_id == request.track_id
                and slot.scene_id == request.scene_id
                and slot.clip_id == clip_id
                for slot in self._project.clip_slots
            ):
                raise ApplicationError(
                    "Clip is not in the requested track/scene slot",
                    code="clip_not_in_slot",
                    status_code=422,
                )
            try:
                action = self._runtime.launch_slot(request.track_id, request.scene_id)
            except (AudioBackendError, EngineError) as error:
                raise ApplicationError(str(error), code="audio_error", status_code=503) from error
            position = self._runtime.snapshot().engine_snapshot.position_frame
            if action.changed and action.target_frame > position:
                self._publish(
                    "clip.scheduled",
                    {
                        "clip_id": str(clip_id),
                        "track_id": str(request.track_id),
                        "scene_id": str(request.scene_id),
                        "target_frame": action.target_frame,
                    },
                )
            return action

    def stop_clip(self, clip_id: UUID, request: ClipStopRequest) -> ScheduledAction:
        with self._lock:
            self._require_open()
            self._require_clip(clip_id)
            self._require_track(request.track_id)
            try:
                action = self._runtime.stop_track(request.track_id)
            except (AudioBackendError, EngineError) as error:
                raise ApplicationError(str(error), code="audio_error", status_code=503) from error
            position = self._runtime.snapshot().engine_snapshot.position_frame
            if action.changed and action.target_frame > position:
                self._publish(
                    "clip.stop_scheduled",
                    {
                        "clip_id": str(clip_id),
                        "track_id": str(request.track_id),
                        "target_frame": action.target_frame,
                    },
                )
            return action

    def stage_audio(self, stream: BinaryIO, original_name: str) -> StagedAudioUpload:
        try:
            return self._repository.stage_audio(stream, original_name)
        except (ProjectArchiveError, WorkingProjectError, OSError, ValueError) as error:
            raise ApplicationError(
                str(error),
                code="asset_upload_invalid",
                status_code=422,
            ) from error

    def resolve_name(self, entity_type: str, name: str) -> UUID:
        return self._commands.resolve_name(entity_type, name)

    def submit_render(self, request: RenderJobRequest) -> BackgroundJob:
        try:
            return self._jobs.submit_render(request)
        except WorkingProjectError as error:
            raise ApplicationError(
                str(error), code="output_policy_error", status_code=422
            ) from error

    def submit_export(self, request: ExportJobRequest) -> BackgroundJob:
        try:
            return self._jobs.submit_export(request)
        except WorkingProjectError as error:
            raise ApplicationError(
                str(error), code="output_policy_error", status_code=422
            ) from error

    def get_job(self, job_id: UUID) -> BackgroundJob:
        return self._jobs.get(job_id)

    def list_jobs(self) -> list[BackgroundJob]:
        return self._jobs.list()

    def cancel_job(self, job_id: UUID) -> BackgroundJob:
        return self._jobs.cancel(job_id)

    def render(self, request: RenderJobRequest) -> RenderMetadata:
        """Compatibility adapter that waits for the asynchronous render job."""

        requested = Path(request.output_path)
        output_name = requested.name if requested.is_absolute() else request.output_path
        safe_request = request.model_copy(update={"output_path": output_name})
        job = self._jobs.wait(self.submit_render(safe_request).job_id)
        if job.state != "completed" or job.output_path is None:
            message = job.error.message if job.error is not None else "Render did not complete"
            raise ApplicationError(message, code="render_error", status_code=422)
        info = sf.info(job.output_path)
        return RenderMetadata(
            project_id=job.project_id,
            revision=job.revision,
            output_path=Path(job.output_path),
            format=str(info.format),
            subtype=str(info.subtype),
            sample_rate=int(info.samplerate),
            channels=int(info.channels),
            frames=int(info.frames),
            duration_seconds=float(info.duration),
        )

    def list_devices(self) -> list[AudioDeviceModel]:
        return [
            AudioDeviceModel(
                index=device.index,
                name=device.name,
                host_api=device.host_api,
                max_output_channels=device.max_output_channels,
                default_sample_rate=device.default_sample_rate,
            )
            for device in self._runtime.devices()
        ]

    def restart_audio(self, device: int | str | None = None) -> ApplicationSnapshot:
        try:
            self._runtime.restart(device)
        except AudioBackendError as error:
            raise ApplicationError(
                str(error),
                code="audio_device_unavailable",
                status_code=422,
            ) from error
        return self.get_snapshot()

    def resolve_external_change(self, resolution: str) -> None:
        if resolution != "detach_source":
            raise ApplicationError(
                "Only detach_source is supported without discarding working changes.",
                code="unsupported_conflict_resolution",
                status_code=422,
            )
        self._repository.detach_source()
        self._publish("project.external_change_resolved", {"resolution": resolution})

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self._jobs.close()
        self._runtime.close()
        self._repository.close()
        self._events.close()

    def __enter__(self) -> "ApplicationService":
        self._require_open()
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()

    def _refine_runtime_impact(self, result: TransactionResult) -> None:
        if not result.ok or result.runtime_impact == RuntimeImpact.RESET:
            return
        active = self._runtime.snapshot().engine_snapshot.active_clip_ids
        active_tracks = {track_id for track_id, _ in active}
        active_clips = {clip_id for _, clip_id in active}
        if active_tracks.intersection(result.deleted_ids.tracks) or active_clips.intersection(
            result.deleted_ids.clips
        ):
            result.runtime_impact = RuntimeImpact.RESET
            result.runtime_reset_required = True

    def _publish(self, event_type: str, payload: dict[str, object]) -> None:
        with self._lock:
            project = self._project
            self._events.publish(
                EventEnvelope(
                    type=event_type,
                    project_id=project.project_id,
                    revision=project.revision.number,
                    payload=payload,
                )
            )

    def _require_open(self) -> None:
        if self._closed:
            raise ApplicationError(
                "Application service is closed",
                code="service_closed",
                status_code=409,
            )

    def _require_clip(self, clip_id: UUID) -> None:
        if not any(clip.id == clip_id for clip in self._project.clips):
            raise ApplicationError("Clip does not exist", code="clip_not_found", status_code=404)

    def _require_track(self, track_id: UUID) -> None:
        if not any(track.id == track_id for track in self._project.tracks):
            raise ApplicationError("Track does not exist", code="track_not_found", status_code=404)

    def _require_scene(self, scene_id: UUID) -> None:
        if not any(scene.id == scene_id for scene in self._project.scenes):
            raise ApplicationError("Scene does not exist", code="scene_not_found", status_code=404)
