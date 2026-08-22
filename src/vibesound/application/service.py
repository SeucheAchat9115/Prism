"""The shared stateful application service used by future clients."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from threading import RLock
from typing import TypeAlias
from uuid import UUID

from vibesound.application.errors import ApplicationError
from vibesound.application.events import EventHub, EventSubscription
from vibesound.application.types import (
    ApiIssue,
    ApplicationSnapshot,
    AudioSnapshotModel,
    ClipLaunchRequest,
    ClipStopRequest,
    EngineSnapshotModel,
    EventEnvelope,
    RenderJobRequest,
    TransactionRequest,
    TransactionResult,
    TransportRequest,
)
from vibesound.audio import AudioBackend, AudioBackendError, OfflineRenderBackend, PortAudioBackend
from vibesound.engine import EngineError, SessionEngine
from vibesound.engine.sources import ClipSourceProvider
from vibesound.engine.types import ScheduledAction
from vibesound.project import ProjectArchiveError, load_project, save_project, validate_project
from vibesound.project.models import Project
from vibesound.project.validation import project_reference_issues
from vibesound.rendering import RenderError, prepare_archive_playback_project

BackendFactory: TypeAlias = Callable[[Project, ClipSourceProvider], AudioBackend]

_TRANSPORT_PATHS = {
    "tempo_bpm",
    "time_signature_numerator",
    "time_signature_denominator",
    "quantization",
}
_TRACK_MIXER_PATHS = {"gain_db", "pan", "muted", "solo"}
_CLIP_PATHS = {
    "name",
    "gain_db",
    "loop",
    "source_offset_frames",
    "duration_frames",
}


class ApplicationService:
    """Own one validated project, its runtime backend, and API events."""

    def __init__(
        self,
        project_path: Path | str,
        *,
        backend_factory: BackendFactory | None = None,
        renderer: OfflineRenderBackend | None = None,
    ) -> None:
        self._project_path = Path(project_path)
        self._lock = RLock()
        self._events = EventHub()
        self._backend_factory = backend_factory or PortAudioBackend
        self._renderer = renderer or OfflineRenderBackend()
        self._closed = False

        report = validate_project(self._project_path)
        if not report.ok:
            details = "; ".join(f"{issue.path}: {issue.message}" for issue in report.issues)
            raise ApplicationError(
                f"Project archive validation failed: {details}",
                code="invalid_project",
                status_code=422,
            )
        self._project = load_project(self._project_path)
        self._runtime_project, self._backend = self._build_backend(self._project)

    @property
    def project_path(self) -> Path:
        return self._project_path

    @property
    def project_id(self) -> UUID:
        with self._lock:
            self._require_open()
            return self._project.project_id

    def get_project(self) -> Project:
        with self._lock:
            self._require_open()
            return self._project.model_copy(deep=True)

    def get_snapshot(self) -> ApplicationSnapshot:
        with self._lock:
            self._require_open()
            return self._snapshot_unlocked()

    def subscribe(self) -> EventSubscription:
        with self._lock:
            self._require_open()
            return self._events.subscribe()

    def preview_transaction(self, request: TransactionRequest) -> TransactionResult:
        with self._lock:
            self._require_open()
            current_revision = self._project.revision.number
            if request.base_revision != current_revision:
                return self._stale_result(request, current_revision)
            try:
                candidate, changed_paths = self._candidate_from_request(request)
                self._validate_runtime_candidate(candidate)
            except ApplicationError as error:
                return self._failure_result(request, current_revision, error)
            return TransactionResult(
                ok=True,
                committed=False,
                base_revision=request.base_revision,
                before_revision=current_revision,
                after_revision=current_revision,
                current_revision=current_revision,
                changed_paths=changed_paths,
            )

    def commit_transaction(self, request: TransactionRequest) -> TransactionResult:
        with self._lock:
            self._require_open()
            current_revision = self._project.revision.number
            if request.base_revision != current_revision:
                return self._stale_result(request, current_revision)
            try:
                candidate, changed_paths = self._candidate_from_request(request)
                runtime_project, runtime_sources = self._validate_runtime_candidate(candidate)
                replacement = self._backend_factory(runtime_project, runtime_sources)
                if not isinstance(replacement, AudioBackend):
                    raise ApplicationError(
                        "Audio backend factory returned an incompatible backend",
                        code="audio_backend_invalid",
                        status_code=500,
                    )
            except ApplicationError as error:
                return self._failure_result(request, current_revision, error)
            except (AudioBackendError, EngineError, RenderError, OSError, ValueError) as error:
                return self._failure_result(
                    request,
                    current_revision,
                    ApplicationError(
                        f"Could not prepare the transaction: {error}",
                        code="transaction_invalid",
                        status_code=422,
                    ),
                )

            candidate.revision.number = current_revision + 1
            try:
                save_project(self._project_path, candidate)
            except (OSError, ProjectArchiveError, ValueError) as error:
                replacement.close()
                return self._failure_result(
                    request,
                    current_revision,
                    ApplicationError(
                        f"Could not persist the transaction: {error}",
                        code="persistence_error",
                        status_code=500,
                    ),
                )

            old_backend = self._backend
            old_state = old_backend.snapshot().state
            self._project = candidate
            self._runtime_project = runtime_project
            self._backend = replacement
            old_backend.close()
            if old_state.value == "running":
                try:
                    replacement.start()
                except AudioBackendError as error:
                    self._publish(
                        "audio.error",
                        {
                            "code": "backend_restart_failed",
                            "message": str(error),
                        },
                    )
            self._publish(
                "project.changed",
                {
                    "changed_paths": changed_paths,
                    "before_revision": current_revision,
                    "after_revision": candidate.revision.number,
                },
            )
            return TransactionResult(
                ok=True,
                committed=True,
                base_revision=request.base_revision,
                before_revision=current_revision,
                after_revision=candidate.revision.number,
                current_revision=candidate.revision.number,
                changed_paths=changed_paths,
            )

    def transport(self, request: TransportRequest) -> ApplicationSnapshot:
        with self._lock:
            self._require_open()
            try:
                backend_operation = "start" if request.operation == "play" else request.operation
                getattr(self._backend, backend_operation)()
            except (AudioBackendError, EngineError) as error:
                self._publish("audio.error", {"code": "transport_error", "message": str(error)})
                raise ApplicationError(
                    str(error),
                    code="audio_error",
                    status_code=503,
                ) from error
            snapshot = self._snapshot_unlocked()
            self._publish(
                "transport.changed",
                {
                    "operation": request.operation,
                    "state": snapshot.audio.state,
                    "position_frame": snapshot.engine.position_frame,
                },
            )
            return snapshot

    def launch_clip(
        self,
        clip_id: UUID,
        request: ClipLaunchRequest,
    ) -> ScheduledAction:
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
                action = self._backend.launch_slot(request.track_id, request.scene_id)
            except (AudioBackendError, EngineError) as error:
                self._publish("audio.error", {"code": "clip_launch_error", "message": str(error)})
                raise ApplicationError(str(error), code="audio_error", status_code=503) from error
            self._publish(
                "clip.launched",
                {
                    "clip_id": str(clip_id),
                    "track_id": str(request.track_id),
                    "scene_id": str(request.scene_id),
                    "target_frame": action.target_frame,
                    "changed": action.changed,
                },
            )
            return action

    def stop_clip(self, clip_id: UUID, request: ClipStopRequest) -> ScheduledAction:
        with self._lock:
            self._require_open()
            self._require_clip(clip_id)
            self._require_track(request.track_id)
            try:
                action = self._backend.stop_track(request.track_id)
            except (AudioBackendError, EngineError) as error:
                self._publish("audio.error", {"code": "clip_stop_error", "message": str(error)})
                raise ApplicationError(str(error), code="audio_error", status_code=503) from error
            self._publish(
                "clip.stopped",
                {
                    "clip_id": str(clip_id),
                    "track_id": str(request.track_id),
                    "target_frame": action.target_frame,
                    "changed": action.changed,
                },
            )
            return action

    def render(self, request: RenderJobRequest):
        with self._lock:
            self._require_open()
            self._publish(
                "render.started",
                {
                    "output_path": request.output_path,
                    "bars": request.bars,
                    "seconds": request.seconds,
                },
            )
            try:
                metadata = self._renderer.render_project(
                    self._project_path,
                    request.output_path,
                    request.to_domain(),
                )
            except (RenderError, OSError, ValueError) as error:
                self._publish(
                    "render.failed",
                    {"output_path": request.output_path, "message": str(error)},
                )
                raise ApplicationError(
                    str(error),
                    code="render_error",
                    status_code=422,
                ) from error
            self._publish(
                "render.completed",
                {
                    "output_path": str(metadata.output_path),
                    "frames": metadata.frames,
                    "duration_seconds": metadata.duration_seconds,
                },
            )
            return metadata

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._backend.close()
            self._events.close()

    def __enter__(self) -> "ApplicationService":
        self._require_open()
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()

    def _build_backend(self, project: Project):
        try:
            prepared = prepare_archive_playback_project(self._project_path, project)
            backend = self._backend_factory(prepared.project, prepared.sources)
        except (AudioBackendError, EngineError, RenderError, OSError, ValueError) as error:
            raise ApplicationError(
                f"Could not prepare the project audio: {error}",
                code="invalid_project_audio",
                status_code=422,
            ) from error
        if not isinstance(backend, AudioBackend):
            raise ApplicationError(
                "Audio backend factory returned an incompatible backend",
                code="audio_backend_invalid",
                status_code=500,
            )
        return prepared.project, backend

    def _validate_runtime_candidate(self, project: Project):
        issues = project_reference_issues(project)
        if issues:
            first = issues[0]
            raise ApplicationError(
                first.message,
                code=first.code,
                path=first.path,
                status_code=422,
            )
        try:
            prepared = prepare_archive_playback_project(self._project_path, project)
            SessionEngine(prepared.project, prepared.sources)
        except (EngineError, RenderError, OSError, ValueError) as error:
            raise ApplicationError(
                str(error),
                code="invalid_runtime_project",
                status_code=422,
            ) from error
        return prepared.project, prepared.sources

    def _candidate_from_request(self, request: TransactionRequest) -> tuple[Project, list[str]]:
        paths = [operation.path for operation in request.operations]
        if len(paths) != len(set(paths)):
            raise ApplicationError(
                "A transaction cannot set the same path more than once",
                code="duplicate_path",
                status_code=422,
            )
        candidate = self._project.model_copy(deep=True)
        for operation in request.operations:
            self._set_path(candidate, operation.path, operation.value)
        return candidate, paths

    def _set_path(self, project: Project, path: str, value: object) -> None:
        tokens = _path_tokens(path)
        try:
            if tokens == ["name"]:
                project.name = value  # type: ignore[assignment]
                return
            if len(tokens) == 2 and tokens[0] == "transport" and tokens[1] in _TRANSPORT_PATHS:
                setattr(project.transport, tokens[1], value)
                return
            if len(tokens) == 3 and tokens[0] == "tracks":
                track = _entity(project.tracks, tokens[1], "track")
                if tokens[2] == "name":
                    track.name = value  # type: ignore[assignment]
                    return
            if len(tokens) == 4 and tokens[0] == "tracks" and tokens[2] == "mixer":
                track = _entity(project.tracks, tokens[1], "track")
                if tokens[3] in _TRACK_MIXER_PATHS:
                    setattr(track.mixer, tokens[3], value)
                    return
            if len(tokens) == 3 and tokens[0] == "scenes" and tokens[2] == "name":
                scene = _entity(project.scenes, tokens[1], "scene")
                scene.name = value  # type: ignore[assignment]
                return
            if len(tokens) == 3 and tokens[0] == "clips" and tokens[2] in _CLIP_PATHS:
                clip = _entity(project.clips, tokens[1], "clip")
                setattr(clip, tokens[2], value)
                return
        except (TypeError, ValueError) as error:
            raise ApplicationError(
                str(error),
                code="invalid_value",
                path=path,
                status_code=422,
            ) from error
        raise ApplicationError(
            f"Transaction path is not writable: {path}",
            code="unknown_path",
            path=path,
            status_code=422,
        )

    def _snapshot_unlocked(self) -> ApplicationSnapshot:
        backend_snapshot = self._backend.snapshot()
        return ApplicationSnapshot(
            project_id=self._project.project_id,
            revision=self._project.revision.number,
            engine=EngineSnapshotModel.from_snapshot(backend_snapshot.engine_snapshot),
            audio=AudioSnapshotModel.from_snapshot(backend_snapshot),
        )

    def _publish(self, event_type: str, payload: dict[str, object]) -> None:
        self._events.publish(
            EventEnvelope(
                type=event_type,
                project_id=self._project.project_id,
                revision=self._project.revision.number,
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

    def _stale_result(
        self,
        request: TransactionRequest,
        current_revision: int,
    ) -> TransactionResult:
        return TransactionResult(
            ok=False,
            committed=False,
            base_revision=request.base_revision,
            before_revision=current_revision,
            after_revision=current_revision,
            current_revision=current_revision,
            errors=[
                ApiIssue(
                    code="stale_revision",
                    message="Project changed after the transaction was created.",
                )
            ],
        )

    def _failure_result(
        self,
        request: TransactionRequest,
        current_revision: int,
        error: ApplicationError,
    ) -> TransactionResult:
        return TransactionResult(
            ok=False,
            committed=False,
            base_revision=request.base_revision,
            before_revision=current_revision,
            after_revision=current_revision,
            current_revision=current_revision,
            errors=[ApiIssue(code=error.code, path=error.path, message=error.message)],
        )


def _path_tokens(path: str) -> list[str]:
    if not path.startswith("/") or path.endswith("/"):
        raise ApplicationError(
            f"Invalid transaction path: {path}",
            code="invalid_path",
            path=path,
            status_code=422,
        )
    tokens: list[str] = []
    for token in path[1:].split("/"):
        if not token:
            raise ApplicationError(
                f"Invalid transaction path: {path}",
                code="invalid_path",
                path=path,
                status_code=422,
            )
        decoded: list[str] = []
        index = 0
        while index < len(token):
            character = token[index]
            if character != "~":
                decoded.append(character)
                index += 1
                continue
            if index + 1 >= len(token) or token[index + 1] not in "01":
                raise ApplicationError(
                    f"Invalid JSON pointer escape in path: {path}",
                    code="invalid_path",
                    path=path,
                    status_code=422,
                )
            decoded.append("~" if token[index + 1] == "0" else "/")
            index += 2
        tokens.append("".join(decoded))
    return tokens


def _entity(items: list[object], token: str, kind: str):
    try:
        entity_id = UUID(token)
    except ValueError as error:
        raise ApplicationError(
            f"Invalid {kind} ID in transaction path",
            code="invalid_path",
            status_code=422,
        ) from error
    for item in items:
        if getattr(item, "id", None) == entity_id:
            return item
    raise ApplicationError(
        f"{kind.title()} does not exist",
        code=f"{kind}_not_found",
        status_code=404,
    )
