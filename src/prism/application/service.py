"""Composition root for repository, commands, runtime, jobs, and API events."""

from __future__ import annotations

import hashlib
import io
import json
from collections.abc import Iterable
from pathlib import Path
from threading import RLock
from typing import BinaryIO
from uuid import UUID, uuid4, uuid5

import soundfile as sf

from prism.application.commands import ProjectCommandService
from prism.application.errors import ApplicationError
from prism.application.events import EventHub, EventSubscription
from prism.application.jobs import RenderJobService
from prism.application.runtime import AudioRuntimeCoordinator, BackendFactory
from prism.application.types import (
    ApiIssue,
    ApplicationSnapshot,
    AssetImportOperation,
    AudioDeviceModel,
    AudioSnapshotModel,
    BackgroundJob,
    ClipLaunchRequest,
    ClipStopRequest,
    EngineSnapshotModel,
    EventEnvelope,
    ExportJobRequest,
    JobPreview,
    PluginAttachOperation,
    PluginAttachRequest,
    PluginBypassRequest,
    PluginBypassUpdateOperation,
    PluginParameterRequest,
    PluginParameterUpdateOperation,
    PluginStateCaptureRequest,
    PluginStateUpdateOperation,
    RenderJobRequest,
    RuntimeImpact,
    SynthAssetRequest,
    SynthAssetResult,
    TransactionRequest,
    TransactionResult,
    TransportRequest,
)
from prism.audio import AudioBackendError, OfflineRenderBackend
from prism.engine import EngineError
from prism.engine.types import ScheduledAction
from prism.plugins import (
    PluginError,
    PluginManager,
    PluginParameter,
    PluginRegistryDocument,
    PluginTrustRecord,
    PluginWorkerStatus,
)
from prism.project import (
    LayeredValidationReport,
    ProjectArchiveError,
    ProjectRepository,
    StagedAudioUpload,
    WorkingProjectError,
)
from prism.project.errors import ValidationIssue
from prism.project.models import PluginInstance, Project
from prism.project.validation import ValidationStage
from prism.rendering import RenderError
from prism.rendering.types import RenderMetadata
from prism.synthesis import render_native_synth


class ApplicationService:
    """Own the single-writer project process and all application boundaries."""

    def __init__(
        self,
        project_path: Path | str,
        *,
        backend_factory: BackendFactory | None = None,
        renderer: OfflineRenderBackend | None = None,
        plugin_manager: PluginManager | None = None,
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
            self._plugins = plugin_manager or PluginManager()
            self._jobs = RenderJobService(
                self._repository,
                publisher=self._publish,
                plugin_store=self._plugins.store,
            )
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
        report = self._repository.validation_report()
        plugin_issues = list(report.reports[ValidationStage.PLUGIN_COMPATIBILITY])
        try:
            compatibility = self._plugins.compatibility(self.get_project())
            for item in compatibility:
                if item.status not in {"ready", "bypassed"}:
                    plugin_issues.append(
                        ValidationIssue(
                            code=f"plugin_{item.status}",
                            path=f"/plugin_instances/{item.instance_id}",
                            message=item.message,
                        )
                    )
        except PluginError as error:
            plugin_issues.append(
                ValidationIssue(
                    code="plugin_configuration_error",
                    path="/plugin_instances",
                    message=str(error),
                )
            )
        reports: dict[ValidationStage, Iterable[ValidationIssue]] = dict(report.reports)
        reports[ValidationStage.PLUGIN_COMPATIBILITY] = plugin_issues
        return LayeredValidationReport(reports)

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
            self._preflight_plugin_operations(request, result)
            self._refine_runtime_impact(result)
            return result

    def commit_transaction(self, request: TransactionRequest) -> TransactionResult:
        with self._lock:
            self._require_open()
            replay = self._commands.idempotent_replay(request)
            if replay is not None:
                return replay
            preview = self._commands.preview(request)
            self._preflight_plugin_operations(request, preview)
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
            self._sync_plugin_worker(request, result)
            return result

    def plugin_config(self) -> dict[str, object]:
        try:
            return self._plugins.store.load().model_dump(mode="json")
        except PluginError as error:
            raise self._plugin_application_error(error) from error

    def add_plugin_search_path(self, path: Path | str) -> list[str]:
        try:
            paths = self._plugins.add_search_path(path)
            self._publish("plugin.search_paths.changed", {"search_paths": paths})
            return paths
        except (PluginError, OSError) as error:
            raise self._plugin_application_error(error) from error

    def remove_plugin_search_path(self, path: Path | str) -> list[str]:
        try:
            paths = self._plugins.remove_search_path(path)
            self._publish("plugin.search_paths.changed", {"search_paths": paths})
            return paths
        except (PluginError, OSError) as error:
            raise self._plugin_application_error(error) from error

    def trust_plugin(self, path: Path | str) -> PluginTrustRecord:
        try:
            record = self._plugins.trust(path)
            self._publish(
                "plugin.trust.changed",
                {"path": record.path, "trusted": True, "sha256": record.binary_sha256},
            )
            return record
        except (PluginError, OSError) as error:
            raise self._plugin_application_error(error) from error

    def revoke_plugin(self, path: Path | str) -> None:
        try:
            self._plugins.revoke(path)
            self._publish("plugin.trust.changed", {"path": str(path), "trusted": False})
        except (PluginError, OSError) as error:
            raise self._plugin_application_error(error) from error

    def scan_plugins(self) -> PluginRegistryDocument:
        try:
            document = self._plugins.scan()
            self._publish(
                "plugin.registry.changed",
                {
                    "scanned_at": document.scanned_at,
                    "plugin_count": len(document.plugins),
                },
            )
            return document
        except (PluginError, OSError) as error:
            raise self._plugin_application_error(error) from error

    def list_plugins(self) -> PluginRegistryDocument:
        try:
            return self._plugins.list_plugins()
        except PluginError as error:
            raise self._plugin_application_error(error) from error

    def plugin_worker_status(self) -> PluginWorkerStatus:
        return self._plugins.status()

    def restart_plugin_worker(self) -> PluginWorkerStatus:
        try:
            status = self._plugins.restart()
            self._publish("plugin.worker.restarted", status.model_dump(mode="json"))
            return status
        except PluginError as error:
            self._publish("plugin.worker.failed", {"message": str(error)})
            raise self._plugin_application_error(error, status_code=503) from error

    def plugin_compatibility(self) -> list[dict[str, object]]:
        try:
            return [
                item.model_dump(mode="json")
                for item in self._plugins.compatibility(self.get_project())
            ]
        except PluginError as error:
            raise self._plugin_application_error(error) from error

    def attach_plugin(
        self,
        track_id: UUID,
        registry_id: UUID,
        request: PluginAttachRequest,
        *,
        preview: bool = False,
    ) -> TransactionResult:
        try:
            record = self._plugins.require_record(registry_id)
        except PluginError as error:
            raise self._plugin_application_error(error) from error
        transaction = TransactionRequest(
            base_revision=request.base_revision,
            idempotency_key=request.idempotency_key,
            operations=[
                PluginAttachOperation(
                    op="plugin.attach",
                    track_id=track_id,
                    registry_id=record.registry_id,
                    instance_id=request.instance_id,
                    plugin_identifier=record.plugin_identifier,
                    binary_sha256=record.binary_sha256,
                    name=record.name,
                    manufacturer=record.manufacturer,
                    version=record.version,
                    category=record.category,
                )
            ],
        )
        if preview:
            return self.preview_transaction(transaction)
        return self.commit_transaction(transaction)

    def plugin_parameters(self, instance_id: UUID) -> list[PluginParameter]:
        try:
            self._ensure_plugin_loaded(instance_id)
            return self._plugins.parameters(instance_id)
        except (PluginError, OSError) as error:
            raise self._plugin_application_error(error, status_code=503) from error

    def update_plugin_parameter(
        self,
        instance_id: UUID,
        parameter_id: str,
        request: PluginParameterRequest,
        *,
        preview: bool = False,
    ) -> TransactionResult:
        if not preview:
            parameters = {item.id for item in self.plugin_parameters(instance_id)}
            if parameter_id not in parameters:
                raise ApplicationError(
                    f"Plugin parameter does not exist: {parameter_id}",
                    code="plugin_parameter_not_found",
                    status_code=404,
                )
        transaction = TransactionRequest(
            base_revision=request.base_revision,
            idempotency_key=request.idempotency_key,
            operations=[
                PluginParameterUpdateOperation(
                    op="plugin.parameter.update",
                    instance_id=instance_id,
                    parameter_id=parameter_id,
                    raw_value=request.raw_value,
                )
            ],
        )
        if preview:
            return self.preview_transaction(transaction)
        return self.commit_transaction(transaction)

    def update_plugin_bypass(
        self,
        instance_id: UUID,
        request: PluginBypassRequest,
        *,
        preview: bool = False,
    ) -> TransactionResult:
        transaction = TransactionRequest(
            base_revision=request.base_revision,
            idempotency_key=request.idempotency_key,
            operations=[
                PluginBypassUpdateOperation(
                    op="plugin.bypass.update",
                    instance_id=instance_id,
                    bypassed=request.bypassed,
                )
            ],
        )
        if preview:
            return self.preview_transaction(transaction)
        return self.commit_transaction(transaction)

    def capture_plugin_state(
        self,
        instance_id: UUID,
        request: PluginStateCaptureRequest,
    ) -> TransactionResult:
        effect = self._find_plugin_instance(instance_id)
        try:
            previous = (
                self._repository.plugin_state_path(effect).read_bytes()
                if effect.state is not None
                else None
            )
        except (OSError, WorkingProjectError) as error:
            raise self._plugin_application_error(error, status_code=503) from error
        try:
            self._ensure_plugin_loaded(instance_id)
            config = self._plugins.store.load()
            payload = self._plugins.capture_state(instance_id, config.max_state_bytes)
            reference = self._repository.install_plugin_state(instance_id, payload)
            result = self.commit_transaction(
                TransactionRequest(
                    base_revision=request.base_revision,
                    idempotency_key=request.idempotency_key,
                    operations=[
                        PluginStateUpdateOperation(
                            op="plugin.state.update",
                            instance_id=instance_id,
                            member_path=reference.member_path,
                            size_bytes=reference.size_bytes,
                            sha256=reference.sha256,
                        )
                    ],
                )
            )
            if not result.ok:
                self._restore_plugin_state(instance_id, previous)
            else:
                self._publish(
                    "plugin.state.captured",
                    {"instance_id": str(instance_id), "size_bytes": len(payload)},
                )
            return result
        except (PluginError, OSError, WorkingProjectError) as error:
            self._restore_plugin_state(instance_id, previous)
            raise self._plugin_application_error(error, status_code=503) from error

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
            return self._launch_slot_unlocked(clip_id, request.track_id, request.scene_id)

    def launch_slot(self, request: ClipLaunchRequest) -> tuple[UUID, ScheduledAction]:
        """Launch the populated slot identified by a track and scene."""

        with self._lock:
            self._require_open()
            self._require_track(request.track_id)
            self._require_scene(request.scene_id)
            slot = next(
                (
                    item
                    for item in self._project.clip_slots
                    if item.track_id == request.track_id and item.scene_id == request.scene_id
                ),
                None,
            )
            if slot is None or slot.clip_id is None:
                raise ApplicationError(
                    "The requested track/scene slot is empty",
                    code="slot_empty",
                    status_code=404,
                )
            self._require_clip(slot.clip_id)
            return slot.clip_id, self._launch_slot_unlocked(
                slot.clip_id,
                request.track_id,
                request.scene_id,
            )

    def stop_clip(self, clip_id: UUID, request: ClipStopRequest) -> ScheduledAction:
        with self._lock:
            self._require_open()
            self._require_clip(clip_id)
            self._require_track(request.track_id)
            return self._stop_track_unlocked(request.track_id, clip_id=clip_id)

    def stop_track(self, request: ClipStopRequest) -> tuple[UUID | None, ScheduledAction]:
        """Stop the active or pending slot on one track."""

        with self._lock:
            self._require_open()
            self._require_track(request.track_id)
            active = dict(self._runtime.snapshot().engine_snapshot.active_clip_ids)
            clip_id = active.get(request.track_id)
            return clip_id, self._stop_track_unlocked(request.track_id, clip_id=clip_id)

    def stage_audio(
        self,
        stream: BinaryIO,
        original_name: str,
        *,
        upload_id: UUID | None = None,
    ) -> StagedAudioUpload:
        try:
            return self._repository.stage_audio(stream, original_name, upload_id=upload_id)
        except (ProjectArchiveError, WorkingProjectError, OSError, ValueError) as error:
            raise ApplicationError(
                str(error),
                code="asset_upload_invalid",
                status_code=422,
            ) from error

    def discard_upload(self, upload_id: UUID) -> None:
        self._repository.discard_upload(upload_id)

    def generate_synth_asset(
        self,
        request: SynthAssetRequest,
        *,
        preview: bool = False,
    ) -> SynthAssetResult:
        """Render, stage, and revision-check one built-in synth audio asset."""

        with self._lock:
            self._require_open()
            project = self._project
            try:
                rendered = render_native_synth(
                    request.spec,
                    sample_rate=project.transport.sample_rate,
                    tempo_bpm=project.transport.tempo_bpm,
                    beats_per_bar=project.transport.time_signature_numerator,
                )
            except ValueError as error:
                raise ApplicationError(
                    str(error),
                    code="synth_invalid",
                    path="/spec",
                    status_code=422,
                ) from error
            synth_digest = hashlib.sha256(
                json.dumps(
                    {
                        "filename": request.filename,
                        "spec": request.spec.model_dump(mode="json"),
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode("utf-8")
            ).hexdigest()
            asset_id = request.asset_id
            if asset_id is None:
                asset_id = (
                    uuid4()
                    if request.idempotency_key is None
                    else uuid5(
                        project.project_id,
                        f"prism-native-synth:{request.idempotency_key}:{synth_digest}:asset",
                    )
                )
            upload_id = (
                None
                if request.idempotency_key is None
                else uuid5(
                    project.project_id,
                    f"prism-native-synth:{request.idempotency_key}:{synth_digest}:upload",
                )
            )
            upload = self.stage_audio(
                io.BytesIO(rendered.wav_bytes),
                request.filename,
                upload_id=upload_id,
            )
            transaction = TransactionRequest(
                base_revision=request.base_revision,
                idempotency_key=request.idempotency_key,
                operations=[
                    AssetImportOperation(
                        op="asset.import",
                        op_id=f"native-synth:{synth_digest}",
                        upload_id=upload.upload_id,
                        asset_id=asset_id,
                    )
                ],
            )
            try:
                result = (
                    self.preview_transaction(transaction)
                    if preview
                    else self.commit_transaction(transaction)
                )
            finally:
                self.discard_upload(upload.upload_id)
            synth_result = SynthAssetResult(
                ok=result.ok,
                preview=preview,
                asset_id=asset_id,
                filename=request.filename,
                frames=rendered.frames,
                sample_rate=rendered.sample_rate,
                duration_seconds=rendered.duration_seconds,
                sha256=rendered.sha256,
                spec=request.spec,
                transaction=result,
            )
            if result.committed and not result.idempotent_replay:
                self._publish(
                    "synth.asset.generated",
                    {
                        "asset_id": str(asset_id),
                        "filename": request.filename,
                        "preset": request.spec.preset,
                        "sha256": rendered.sha256,
                    },
                )
            return synth_result

    def resolve_name(self, entity_type: str, name: str) -> UUID:
        return self._commands.resolve_name(entity_type, name)

    def submit_render(self, request: RenderJobRequest) -> BackgroundJob:
        try:
            return self._jobs.submit_render(request)
        except WorkingProjectError as error:
            raise ApplicationError(
                str(error), code="output_policy_error", status_code=422
            ) from error

    def preview_render(self, request: RenderJobRequest) -> JobPreview:
        try:
            return self._jobs.preview_render(request)
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

    def preview_export(self, request: ExportJobRequest) -> JobPreview:
        try:
            return self._jobs.preview_export(request)
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
        self._plugins.close()
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

    def _preflight_plugin_operations(
        self,
        request: TransactionRequest,
        result: TransactionResult,
    ) -> None:
        if not result.ok:
            return
        for operation in request.operations:
            if not isinstance(operation, PluginAttachOperation):
                continue
            try:
                record = self._plugins.require_record(operation.registry_id)
            except PluginError as error:
                result.ok = False
                result.errors.append(
                    ApiIssue(code="plugin_unavailable", message=str(error))
                )
                return
            expected = {
                "plugin_identifier": record.plugin_identifier,
                "binary_sha256": record.binary_sha256,
                "name": record.name,
                "manufacturer": record.manufacturer,
                "version": record.version,
                "category": record.category,
            }
            if any(getattr(operation, field) != value for field, value in expected.items()):
                result.ok = False
                result.errors.append(
                    ApiIssue(
                        code="plugin_registry_mismatch",
                        message="Plugin metadata must match the current trusted registry entry.",
                    )
                )
                return

    def _sync_plugin_worker(
        self,
        request: TransactionRequest,
        result: TransactionResult,
    ) -> None:
        try:
            for operation in request.operations:
                if (
                    isinstance(operation, PluginParameterUpdateOperation)
                    and self._plugins.is_loaded(operation.instance_id)
                ):
                    self._plugins.set_parameter(
                        operation.instance_id,
                        operation.parameter_id,
                        operation.raw_value,
                    )
                elif (
                    isinstance(operation, PluginBypassUpdateOperation)
                    and self._plugins.is_loaded(operation.instance_id)
                ):
                    self._plugins.set_bypass(operation.instance_id, operation.bypassed)
            for instance_id in result.deleted_ids.plugin_instances:
                self._plugins.unload(instance_id)
                self._repository.remove_plugin_state(instance_id)
        except (PluginError, OSError) as error:
            result.warnings.append(
                ApiIssue(
                    code="plugin_worker_sync_failed",
                    message=f"Project committed but plugin worker sync failed: {error}",
                )
            )
            self._publish("plugin.worker.failed", {"message": str(error)})

    def _find_plugin_instance(self, instance_id: UUID) -> PluginInstance:
        for track in self._project.tracks:
            for effect in track.effects:
                if effect.id == instance_id:
                    return effect
        raise ApplicationError(
            f"Plugin instance does not exist: {instance_id}",
            code="plugin_instance_not_found",
            status_code=404,
        )

    def _ensure_plugin_loaded(self, instance_id: UUID) -> PluginInstance:
        effect = self._find_plugin_instance(instance_id)
        if self._plugins.is_loaded(instance_id):
            return effect
        state = (
            self._repository.plugin_state_path(effect).read_bytes()
            if effect.state is not None
            else None
        )
        self._plugins.load_instance(
            effect,
            sample_rate=self._project.transport.sample_rate,
            state=state,
        )
        self._publish(
            "plugin.instance.loaded",
            {"instance_id": str(effect.id), "registry_id": str(effect.registry_id)},
        )
        return effect

    def _restore_plugin_state(self, instance_id: UUID, payload: bytes | None) -> None:
        if payload is None:
            self._repository.remove_plugin_state(instance_id)
        else:
            self._repository.install_plugin_state(instance_id, payload)

    @staticmethod
    def _plugin_application_error(
        error: Exception,
        *,
        status_code: int = 422,
    ) -> ApplicationError:
        return ApplicationError(
            str(error),
            code="plugin_error",
            status_code=status_code,
        )

    def _launch_slot_unlocked(
        self,
        clip_id: UUID,
        track_id: UUID,
        scene_id: UUID,
    ) -> ScheduledAction:
        try:
            action = self._runtime.launch_slot(track_id, scene_id)
        except (AudioBackendError, EngineError) as error:
            raise ApplicationError(str(error), code="audio_error", status_code=503) from error
        position = self._runtime.snapshot().engine_snapshot.position_frame
        if action.changed and action.target_frame > position:
            self._publish(
                "clip.scheduled",
                {
                    "clip_id": str(clip_id),
                    "track_id": str(track_id),
                    "scene_id": str(scene_id),
                    "target_frame": action.target_frame,
                },
            )
        return action

    def _stop_track_unlocked(
        self,
        track_id: UUID,
        *,
        clip_id: UUID | None,
    ) -> ScheduledAction:
        try:
            action = self._runtime.stop_track(track_id)
        except (AudioBackendError, EngineError) as error:
            raise ApplicationError(str(error), code="audio_error", status_code=503) from error
        position = self._runtime.snapshot().engine_snapshot.position_frame
        if action.changed and action.target_frame > position:
            self._publish(
                "clip.stop_scheduled",
                {
                    "clip_id": None if clip_id is None else str(clip_id),
                    "track_id": str(track_id),
                    "target_frame": action.target_frame,
                },
            )
        return action

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
