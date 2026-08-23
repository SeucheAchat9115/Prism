"""Typed, revisioned project authoring operations."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4, uuid5

from prism.application.errors import ApplicationError
from prism.application.types import (
    ApiIssue,
    AssetDeleteOperation,
    AssetImportOperation,
    CascadeImpact,
    ClipCreateOperation,
    ClipDeleteOperation,
    ClipDuplicateOperation,
    ClipUpdateOperation,
    EntityChanges,
    MixerUpdateOperation,
    ProjectRenameOperation,
    RuntimeImpact,
    SceneCreateOperation,
    SceneDeleteOperation,
    SceneRenameOperation,
    SceneReorderOperation,
    SetOperation,
    SlotAssignOperation,
    SlotClearOperation,
    SlotReplaceOperation,
    TrackCreateOperation,
    TrackDeleteOperation,
    TrackRenameOperation,
    TrackReorderOperation,
    TransactionRequest,
    TransactionResult,
    TransportUpdateOperation,
)
from prism.project import (
    ExternalProjectChangeError,
    ProjectRepository,
    ProjectValidationError,
    StagedUploadError,
    WorkingProjectError,
)
from prism.project.models import (
    AssetReference,
    AudioClip,
    ClipSlot,
    Project,
    Scene,
    Track,
)
from prism.project.validation import project_playback_issues, project_reference_issues

_IMPACT_RANK = {
    RuntimeImpact.NONE: 0,
    RuntimeImpact.INCREMENTAL: 1,
    RuntimeImpact.REBUILD: 2,
    RuntimeImpact.RESET: 3,
}
_TRANSPORT_FIELDS = {
    "tempo_bpm",
    "sample_rate",
    "time_signature_numerator",
    "time_signature_denominator",
    "quantization",
}
_MIXER_FIELDS = {"gain_db", "pan", "muted", "solo"}
_CLIP_FIELDS = {
    "name",
    "asset_id",
    "gain_db",
    "loop",
    "source_offset_frames",
    "duration_frames",
}


@dataclass(slots=True)
class CommandPlan:
    """A validated candidate plus deferred asset installation work."""

    request: TransactionRequest
    candidate: Project
    result: TransactionResult
    installs: list[tuple[UUID, UUID]] = field(default_factory=list)


@dataclass(slots=True)
class _Mutation:
    project: Project
    changed_paths: list[str] = field(default_factory=list)
    created: dict[str, set[UUID]] = field(default_factory=lambda: _change_sets())
    changed: dict[str, set[UUID]] = field(default_factory=lambda: _change_sets())
    deleted: dict[str, set[UUID]] = field(default_factory=lambda: _change_sets())
    cascades: list[CascadeImpact] = field(default_factory=list)
    installs: list[tuple[UUID, UUID]] = field(default_factory=list)
    impact: RuntimeImpact = RuntimeImpact.NONE

    def mark_impact(self, impact: RuntimeImpact) -> None:
        if _IMPACT_RANK[impact] > _IMPACT_RANK[self.impact]:
            self.impact = impact


class ProjectCommandService:
    """Preview and atomically apply typed operations to one repository."""

    def __init__(self, repository: ProjectRepository) -> None:
        self._repository = repository

    def preview(self, request: TransactionRequest) -> TransactionResult:
        plan = self.prepare(request)
        return plan.result

    def prepare(self, request: TransactionRequest) -> CommandPlan:
        current = self._repository.get_project()
        mutation = _Mutation(current.model_copy(deep=True))
        if request.base_revision != current.revision.number:
            return CommandPlan(
                request,
                mutation.project,
                _failure_result(
                    request,
                    current.revision.number,
                    "stale_revision",
                    "Project changed after the transaction was created.",
                ),
            )
        try:
            op_ids = [
                operation.op_id
                for operation in request.operations
                if operation.op_id is not None
            ]
            if len(op_ids) != len(set(op_ids)):
                raise ApplicationError(
                    "Operation IDs must be unique within a transaction.",
                    code="duplicate_operation_id",
                    status_code=422,
                )
            set_paths = [
                operation.path
                for operation in request.operations
                if isinstance(operation, SetOperation)
            ]
            if len(set_paths) != len(set(set_paths)):
                raise ApplicationError(
                    "A transaction cannot set the same path more than once.",
                    code="duplicate_path",
                    status_code=422,
                )
            for index, operation in enumerate(request.operations):
                self._apply_operation(mutation, operation, index, request)
            issues = (*project_reference_issues(mutation.project), *project_playback_issues(
                mutation.project
            ))
            if issues:
                issue = issues[0]
                raise ApplicationError(
                    issue.message,
                    code=issue.code,
                    path=issue.path,
                    status_code=422,
                )
        except (ApplicationError, StagedUploadError, WorkingProjectError, ValueError) as error:
            if isinstance(error, ApplicationError):
                code, path, message = error.code, error.path, error.message
            elif isinstance(error, StagedUploadError):
                code, path, message = "upload_not_found", "", str(error)
            elif isinstance(error, ValueError):
                code, path, message = "invalid_value", "", str(error)
            else:
                code, path, message = "invalid_operation", "", str(error)
            result = self._result(mutation, request, current.revision.number)
            result.ok = False
            result.errors.append(ApiIssue(code=code, path=path, message=message))
            return CommandPlan(request, mutation.project, result, mutation.installs)

        mutation.project.revision.number = current.revision.number + 1
        result = self._result(mutation, request, current.revision.number)
        return CommandPlan(request, mutation.project, result, mutation.installs)

    def commit(self, request: TransactionRequest) -> tuple[TransactionResult, Project | None]:
        digest = _request_digest(request)
        replay = self.idempotent_replay(request)
        if replay is not None:
            return replay, self._repository.get_project() if replay.ok else None

        plan = self.prepare(request)
        if not plan.result.ok:
            return plan.result, None
        if plan.result.runtime_reset_required and not request.allow_runtime_reset:
            plan.result.ok = False
            plan.result.errors.append(
                ApiIssue(
                    code="runtime_reset_required",
                    message=(
                        "This transaction requires a runtime reset; preview it and retry with "
                        "allow_runtime_reset=true."
                    ),
                )
            )
            return plan.result, None

        installed: list[tuple[UUID, UUID]] = []
        try:
            for upload_id, asset_id in plan.installs:
                self._repository.install_upload(upload_id, asset_id)
                installed.append((upload_id, asset_id))
            committed = self._repository.commit_project(
                plan.candidate,
                history={
                    "kind": "transaction",
                    "request_sha256": digest,
                    "idempotency_key": request.idempotency_key,
                    "operations": [
                        operation.model_dump(mode="json") for operation in request.operations
                    ],
                },
            )
        except ExternalProjectChangeError as error:
            return (
                _failure_result(
                    request,
                    self._repository.get_project().revision.number,
                    "external_project_change",
                    str(error),
                ),
                None,
            )
        except (ProjectValidationError, WorkingProjectError, OSError) as error:
            self._repository.rollback_installs(installed)
            return (
                _failure_result(
                    request,
                    self._repository.get_project().revision.number,
                    "persistence_error",
                    f"Could not persist the transaction: {error}",
                ),
                None,
            )

        for upload_id, _ in installed:
            self._repository.discard_upload(upload_id)
        plan.result.committed = True
        plan.result.after_revision = committed.revision.number
        plan.result.current_revision = committed.revision.number
        if request.idempotency_key is not None:
            self._repository.put_idempotency(
                request.idempotency_key,
                digest,
                plan.result.model_dump(mode="json"),
            )
        return plan.result, committed

    def idempotent_replay(self, request: TransactionRequest) -> TransactionResult | None:
        """Return a stored retry before current-state validation changes its meaning."""

        if request.idempotency_key is None:
            return None
        stored = self._repository.get_idempotency(request.idempotency_key)
        if stored is None:
            return None
        if stored["request_sha256"] != _request_digest(request):
            current = self._repository.get_project().revision.number
            return _failure_result(
                request,
                current,
                "idempotency_conflict",
                "The idempotency key was already used for another request.",
            )
        replay = TransactionResult.model_validate(stored["result"])
        replay.idempotent_replay = True
        return replay

    def resolve_name(self, entity_type: str, name: str) -> UUID:
        project = self._repository.get_project()
        collections: dict[str, list[Any]] = {
            "track": project.tracks,
            "scene": project.scenes,
            "clip": project.clips,
            "asset": project.assets,
        }
        try:
            items = collections[entity_type]
        except KeyError as error:
            raise ApplicationError(
                f"Unknown entity type: {entity_type}",
                code="unknown_entity_type",
                status_code=404,
            ) from error
        target = name.strip().casefold()
        matches = [
            item
            for item in items
            if str(getattr(item, "name", getattr(item, "original_name", ""))).casefold()
            == target
        ]
        if not matches:
            raise ApplicationError(
                f"No {entity_type} has the exact name {name!r}",
                code="name_not_found",
                status_code=404,
            )
        if len(matches) > 1:
            raise ApplicationError(
                f"More than one {entity_type} has the exact name {name!r}",
                code="ambiguous_name",
                status_code=409,
            )
        return UUID(str(getattr(matches[0], "id")))

    def _result(
        self,
        mutation: _Mutation,
        request: TransactionRequest,
        revision: int,
    ) -> TransactionResult:
        return TransactionResult(
            ok=True,
            committed=False,
            base_revision=request.base_revision,
            before_revision=revision,
            after_revision=revision,
            current_revision=revision,
            changed_paths=_unique(mutation.changed_paths),
            created_ids=_entity_changes(mutation.created),
            changed_ids=_entity_changes(mutation.changed),
            deleted_ids=_entity_changes(mutation.deleted),
            cascade_impact=mutation.cascades,
            runtime_impact=mutation.impact,
            runtime_reset_required=mutation.impact == RuntimeImpact.RESET,
        )

    def _apply_operation(
        self,
        mutation: _Mutation,
        operation: Any,
        index: int,
        request: TransactionRequest,
    ) -> None:
        project = mutation.project
        if isinstance(operation, SetOperation):
            _apply_legacy_set(mutation, operation)
        elif isinstance(operation, ProjectRenameOperation):
            project.name = operation.name
            mutation.changed_paths.append("/name")
        elif isinstance(operation, TrackCreateOperation):
            entity_id = operation.track_id or _created_id(project, request, operation, index)
            _require_unused_id(project, entity_id)
            track = Track(
                id=entity_id,
                name=operation.name,
                order=len(project.tracks),
            )
            project.tracks.append(track)
            if operation.order is not None:
                _reorder(mutation, "tracks", track.id, operation.order)
            mutation.created["tracks"].add(track.id)
            mutation.changed_paths.append(f"/tracks/{track.id}")
            mutation.mark_impact(RuntimeImpact.REBUILD)
        elif isinstance(operation, TrackRenameOperation):
            track = _entity(project.tracks, operation.track_id, "track")
            track.name = operation.name
            mutation.changed["tracks"].add(track.id)
            mutation.changed_paths.append(f"/tracks/{track.id}/name")
        elif isinstance(operation, TrackReorderOperation):
            _reorder(mutation, "tracks", operation.track_id, operation.order)
            mutation.mark_impact(RuntimeImpact.REBUILD)
        elif isinstance(operation, TrackDeleteOperation):
            _delete_track(mutation, operation, index)
        elif isinstance(operation, SceneCreateOperation):
            entity_id = operation.scene_id or _created_id(project, request, operation, index)
            _require_unused_id(project, entity_id)
            scene = Scene(id=entity_id, name=operation.name, order=len(project.scenes))
            project.scenes.append(scene)
            if operation.order is not None:
                _reorder(mutation, "scenes", scene.id, operation.order)
            mutation.created["scenes"].add(scene.id)
            mutation.changed_paths.append(f"/scenes/{scene.id}")
            mutation.mark_impact(RuntimeImpact.REBUILD)
        elif isinstance(operation, SceneRenameOperation):
            scene = _entity(project.scenes, operation.scene_id, "scene")
            scene.name = operation.name
            mutation.changed["scenes"].add(scene.id)
            mutation.changed_paths.append(f"/scenes/{scene.id}/name")
        elif isinstance(operation, SceneReorderOperation):
            _reorder(mutation, "scenes", operation.scene_id, operation.order)
            mutation.mark_impact(RuntimeImpact.REBUILD)
        elif isinstance(operation, SceneDeleteOperation):
            _delete_scene(mutation, operation, index)
        elif isinstance(operation, AssetImportOperation):
            upload = self._repository.get_upload(operation.upload_id)
            asset_id = operation.asset_id or _created_id(project, request, operation, index)
            _require_unused_id(project, asset_id)
            asset = AssetReference(
                id=asset_id,
                member_path=f"assets/audio/{asset_id}{upload.suffix}",
                original_name=upload.original_name,
                size_bytes=upload.size_bytes,
                sha256=upload.sha256,
                sample_rate=upload.sample_rate,
                channels=upload.channels,
                frames=upload.frames,
                format=upload.format,
            )
            project.assets.append(asset)
            mutation.installs.append((operation.upload_id, asset_id))
            mutation.created["assets"].add(asset_id)
            mutation.changed_paths.append(f"/assets/{asset_id}")
        elif isinstance(operation, AssetDeleteOperation):
            _delete_asset(mutation, operation, index)
        elif isinstance(operation, ClipCreateOperation):
            _entity(project.assets, operation.asset_id, "asset")
            clip_id = operation.clip_id or _created_id(project, request, operation, index)
            _require_unused_id(project, clip_id)
            clip = AudioClip(
                id=clip_id,
                name=operation.name,
                asset_id=operation.asset_id,
                source_offset_frames=operation.source_offset_frames,
                duration_frames=operation.duration_frames,
                gain_db=operation.gain_db,
                loop=operation.loop,
            )
            project.clips.append(clip)
            mutation.created["clips"].add(clip.id)
            mutation.changed_paths.append(f"/clips/{clip.id}")
            mutation.mark_impact(RuntimeImpact.REBUILD)
        elif isinstance(operation, ClipUpdateOperation):
            clip = _entity(project.clips, operation.clip_id, "clip")
            if operation.asset_id is not None:
                _entity(project.assets, operation.asset_id, "asset")
            fields = {
                name
                for name in operation.model_fields_set & _CLIP_FIELDS
                if getattr(operation, name) is not None
            }
            for name in sorted(fields):
                setattr(clip, name, getattr(operation, name))
                mutation.changed_paths.append(f"/clips/{clip.id}/{name}")
            if operation.clear_duration:
                clip.duration_frames = None
                mutation.changed_paths.append(f"/clips/{clip.id}/duration_frames")
            mutation.changed["clips"].add(clip.id)
            mutation.mark_impact(RuntimeImpact.REBUILD)
        elif isinstance(operation, ClipDuplicateOperation):
            original = _entity(project.clips, operation.clip_id, "clip")
            clip_id = operation.new_clip_id or _created_id(project, request, operation, index)
            _require_unused_id(project, clip_id)
            duplicate = original.model_copy(
                update={"id": clip_id, "name": operation.name or f"{original.name} copy"}
            )
            project.clips.append(duplicate)
            mutation.created["clips"].add(duplicate.id)
            mutation.changed_paths.append(f"/clips/{duplicate.id}")
            mutation.mark_impact(RuntimeImpact.REBUILD)
        elif isinstance(operation, ClipDeleteOperation):
            _delete_clip(mutation, operation, index)
        elif isinstance(operation, SlotAssignOperation):
            _assign_slot(mutation, operation, request, index)
        elif isinstance(operation, SlotReplaceOperation):
            _replace_slot(mutation, operation)
        elif isinstance(operation, SlotClearOperation):
            _clear_slot(mutation, operation)
        elif isinstance(operation, TransportUpdateOperation):
            fields = {
                name
                for name in operation.model_fields_set & _TRANSPORT_FIELDS
                if getattr(operation, name) is not None
            }
            for name in sorted(fields):
                setattr(project.transport, name, getattr(operation, name))
                mutation.changed_paths.append(f"/transport/{name}")
            mutation.mark_impact(
                RuntimeImpact.RESET if "sample_rate" in fields else RuntimeImpact.REBUILD
            )
        elif isinstance(operation, MixerUpdateOperation):
            track = _entity(project.tracks, operation.track_id, "track")
            fields = {
                name
                for name in operation.model_fields_set & _MIXER_FIELDS
                if getattr(operation, name) is not None
            }
            for name in sorted(fields):
                setattr(track.mixer, name, getattr(operation, name))
                mutation.changed_paths.append(f"/tracks/{track.id}/mixer/{name}")
            mutation.changed["tracks"].add(track.id)
            mutation.mark_impact(RuntimeImpact.INCREMENTAL)
        else:  # pragma: no cover - discriminated contract guards this boundary
            raise ApplicationError(
                "Unsupported project operation",
                code="unknown_operation",
                status_code=422,
            )


def _change_sets() -> dict[str, set[UUID]]:
    return {name: set() for name in ("tracks", "scenes", "assets", "clips", "slots")}


def _entity_changes(values: dict[str, set[UUID]]) -> EntityChanges:
    return EntityChanges(**{name: sorted(ids, key=str) for name, ids in values.items()})


def _created_id(
    project: Project,
    request: TransactionRequest,
    operation: Any,
    index: int,
) -> UUID:
    token = operation.op_id or str(index)
    if request.idempotency_key is None and operation.op_id is None:
        return uuid4()
    return uuid5(
        project.project_id,
        f"{request.idempotency_key or 'operation'}:{operation.op}:{token}",
    )


def _require_unused_id(project: Project, entity_id: UUID) -> None:
    for collection in (
        project.tracks,
        project.scenes,
        project.assets,
        project.clips,
        project.clip_slots,
    ):
        if any(item.id == entity_id for item in collection):
            raise ApplicationError(
                f"Entity ID already exists: {entity_id}",
                code="duplicate_id",
                status_code=409,
            )


def _entity(items: list[Any], entity_id: UUID, kind: str) -> Any:
    for item in items:
        if item.id == entity_id:
            return item
    raise ApplicationError(
        f"{kind.title()} does not exist: {entity_id}",
        code=f"{kind}_not_found",
        status_code=404,
    )


def _reorder(mutation: _Mutation, collection_name: str, entity_id: UUID, order: int) -> None:
    items = getattr(mutation.project, collection_name)
    kind = collection_name[:-1]
    moving = _entity(items, entity_id, kind)
    ordered = sorted(items, key=lambda item: (item.order, str(item.id)))
    ordered.remove(moving)
    ordered.insert(min(order, len(ordered)), moving)
    for position, item in enumerate(ordered):
        if item.order != position:
            item.order = position
            mutation.changed[collection_name].add(item.id)
            mutation.changed_paths.append(f"/{collection_name}/{item.id}/order")
    setattr(mutation.project, collection_name, ordered)


def _delete_track(mutation: _Mutation, operation: TrackDeleteOperation, index: int) -> None:
    project = mutation.project
    _entity(project.tracks, operation.track_id, "track")
    slots = [slot for slot in project.clip_slots if slot.track_id == operation.track_id]
    cascade = CascadeImpact(
        operation_index=index,
        entity_type="track",
        entity_id=operation.track_id,
        dependent_ids=EntityChanges(slots=[slot.id for slot in slots]),
    )
    if slots:
        mutation.cascades.append(cascade)
    if slots and not operation.cascade:
        raise ApplicationError(
            "Track has dependent slots; preview and retry with cascade=true.",
            code="cascade_required",
            status_code=409,
        )
    project.tracks = [track for track in project.tracks if track.id != operation.track_id]
    project.clip_slots = [
        slot for slot in project.clip_slots if slot.track_id != operation.track_id
    ]
    mutation.deleted["tracks"].add(operation.track_id)
    mutation.deleted["slots"].update(slot.id for slot in slots)
    mutation.changed_paths.append(f"/tracks/{operation.track_id}")
    _normalize_orders(mutation, "tracks")
    mutation.mark_impact(RuntimeImpact.REBUILD)


def _delete_scene(mutation: _Mutation, operation: SceneDeleteOperation, index: int) -> None:
    project = mutation.project
    _entity(project.scenes, operation.scene_id, "scene")
    slots = [slot for slot in project.clip_slots if slot.scene_id == operation.scene_id]
    cascade = CascadeImpact(
        operation_index=index,
        entity_type="scene",
        entity_id=operation.scene_id,
        dependent_ids=EntityChanges(slots=[slot.id for slot in slots]),
    )
    if slots:
        mutation.cascades.append(cascade)
    if slots and not operation.cascade:
        raise ApplicationError(
            "Scene has dependent slots; preview and retry with cascade=true.",
            code="cascade_required",
            status_code=409,
        )
    project.scenes = [scene for scene in project.scenes if scene.id != operation.scene_id]
    project.clip_slots = [
        slot for slot in project.clip_slots if slot.scene_id != operation.scene_id
    ]
    mutation.deleted["scenes"].add(operation.scene_id)
    mutation.deleted["slots"].update(slot.id for slot in slots)
    mutation.changed_paths.append(f"/scenes/{operation.scene_id}")
    _normalize_orders(mutation, "scenes")
    mutation.mark_impact(RuntimeImpact.REBUILD)


def _delete_clip(mutation: _Mutation, operation: ClipDeleteOperation, index: int) -> None:
    project = mutation.project
    _entity(project.clips, operation.clip_id, "clip")
    slots = [slot for slot in project.clip_slots if slot.clip_id == operation.clip_id]
    if slots:
        mutation.cascades.append(
            CascadeImpact(
                operation_index=index,
                entity_type="clip",
                entity_id=operation.clip_id,
                dependent_ids=EntityChanges(slots=[slot.id for slot in slots]),
            )
        )
    if slots and not operation.cascade:
        raise ApplicationError(
            "Clip is assigned to slots; preview and retry with cascade=true.",
            code="cascade_required",
            status_code=409,
        )
    project.clips = [clip for clip in project.clips if clip.id != operation.clip_id]
    for slot in slots:
        slot.clip_id = None
        mutation.changed["slots"].add(slot.id)
        mutation.changed_paths.append(f"/clip_slots/{slot.id}/clip_id")
    mutation.deleted["clips"].add(operation.clip_id)
    mutation.changed_paths.append(f"/clips/{operation.clip_id}")
    mutation.mark_impact(RuntimeImpact.REBUILD)


def _delete_asset(mutation: _Mutation, operation: AssetDeleteOperation, index: int) -> None:
    project = mutation.project
    _entity(project.assets, operation.asset_id, "asset")
    clips = [clip for clip in project.clips if clip.asset_id == operation.asset_id]
    clip_ids = {clip.id for clip in clips}
    slots = [slot for slot in project.clip_slots if slot.clip_id in clip_ids]
    if clips or slots:
        mutation.cascades.append(
            CascadeImpact(
                operation_index=index,
                entity_type="asset",
                entity_id=operation.asset_id,
                dependent_ids=EntityChanges(
                    clips=[clip.id for clip in clips],
                    slots=[slot.id for slot in slots],
                ),
            )
        )
    if (clips or slots) and not operation.cascade:
        raise ApplicationError(
            "Asset has dependent clips; preview and retry with cascade=true.",
            code="cascade_required",
            status_code=409,
        )
    project.assets = [asset for asset in project.assets if asset.id != operation.asset_id]
    project.clips = [clip for clip in project.clips if clip.id not in clip_ids]
    for slot in slots:
        slot.clip_id = None
        mutation.changed["slots"].add(slot.id)
        mutation.changed_paths.append(f"/clip_slots/{slot.id}/clip_id")
    mutation.deleted["assets"].add(operation.asset_id)
    mutation.deleted["clips"].update(clip_ids)
    mutation.changed_paths.append(f"/assets/{operation.asset_id}")
    mutation.mark_impact(RuntimeImpact.REBUILD if clips else RuntimeImpact.NONE)


def _assign_slot(
    mutation: _Mutation,
    operation: SlotAssignOperation,
    request: TransactionRequest,
    index: int,
) -> None:
    project = mutation.project
    _entity(project.tracks, operation.track_id, "track")
    _entity(project.scenes, operation.scene_id, "scene")
    _entity(project.clips, operation.clip_id, "clip")
    existing = _slot(project, operation.track_id, operation.scene_id)
    if existing is not None and existing.clip_id is not None:
        raise ApplicationError(
            "The track/scene slot is already occupied; use slot.replace.",
            code="slot_occupied",
            status_code=409,
        )
    if existing is not None:
        existing.clip_id = operation.clip_id
        mutation.changed["slots"].add(existing.id)
        mutation.changed_paths.append(f"/clip_slots/{existing.id}/clip_id")
    else:
        slot_id = operation.slot_id or _created_id(project, request, operation, index)
        _require_unused_id(project, slot_id)
        slot = ClipSlot(
            id=slot_id,
            track_id=operation.track_id,
            scene_id=operation.scene_id,
            clip_id=operation.clip_id,
        )
        project.clip_slots.append(slot)
        mutation.created["slots"].add(slot.id)
        mutation.changed_paths.append(f"/clip_slots/{slot.id}")
    mutation.mark_impact(RuntimeImpact.REBUILD)


def _replace_slot(mutation: _Mutation, operation: SlotReplaceOperation) -> None:
    project = mutation.project
    _entity(project.tracks, operation.track_id, "track")
    _entity(project.scenes, operation.scene_id, "scene")
    _entity(project.clips, operation.clip_id, "clip")
    slot = _slot(project, operation.track_id, operation.scene_id)
    if slot is None:
        raise ApplicationError(
            "The track/scene slot does not exist; use slot.assign.",
            code="slot_not_found",
            status_code=404,
        )
    slot.clip_id = operation.clip_id
    mutation.changed["slots"].add(slot.id)
    mutation.changed_paths.append(f"/clip_slots/{slot.id}/clip_id")
    mutation.mark_impact(RuntimeImpact.REBUILD)


def _clear_slot(mutation: _Mutation, operation: SlotClearOperation) -> None:
    slot = _slot(mutation.project, operation.track_id, operation.scene_id)
    if slot is None:
        raise ApplicationError(
            "The track/scene slot does not exist.",
            code="slot_not_found",
            status_code=404,
        )
    if slot.clip_id is not None:
        slot.clip_id = None
        mutation.changed["slots"].add(slot.id)
        mutation.changed_paths.append(f"/clip_slots/{slot.id}/clip_id")
        mutation.mark_impact(RuntimeImpact.REBUILD)


def _slot(project: Project, track_id: UUID, scene_id: UUID) -> ClipSlot | None:
    return next(
        (
            slot
            for slot in project.clip_slots
            if slot.track_id == track_id and slot.scene_id == scene_id
        ),
        None,
    )


def _normalize_orders(mutation: _Mutation, collection_name: str) -> None:
    items = sorted(
        getattr(mutation.project, collection_name),
        key=lambda item: (item.order, str(item.id)),
    )
    for position, item in enumerate(items):
        if item.order != position:
            item.order = position
            mutation.changed[collection_name].add(item.id)
            mutation.changed_paths.append(f"/{collection_name}/{item.id}/order")
    setattr(mutation.project, collection_name, items)


def _apply_legacy_set(mutation: _Mutation, operation: SetOperation) -> None:
    project = mutation.project
    path = operation.path
    tokens = _path_tokens(path)
    if tokens == ["name"]:
        project.name = operation.value
        mutation.changed_paths.append(path)
        return
    if len(tokens) == 2 and tokens[0] == "transport" and tokens[1] in _TRANSPORT_FIELDS:
        setattr(project.transport, tokens[1], operation.value)
        mutation.changed_paths.append(path)
        mutation.mark_impact(
            RuntimeImpact.RESET if tokens[1] == "sample_rate" else RuntimeImpact.REBUILD
        )
        return
    if len(tokens) == 3 and tokens[0] == "tracks" and tokens[2] == "name":
        track = _entity(project.tracks, _uuid_token(tokens[1], path), "track")
        track.name = operation.value
        mutation.changed["tracks"].add(track.id)
        mutation.changed_paths.append(path)
        return
    if len(tokens) == 4 and tokens[0] == "tracks" and tokens[2] == "mixer":
        if tokens[3] in _MIXER_FIELDS:
            track = _entity(project.tracks, _uuid_token(tokens[1], path), "track")
            setattr(track.mixer, tokens[3], operation.value)
            mutation.changed["tracks"].add(track.id)
            mutation.changed_paths.append(path)
            mutation.mark_impact(RuntimeImpact.INCREMENTAL)
            return
    if len(tokens) == 3 and tokens[0] == "scenes" and tokens[2] == "name":
        scene = _entity(project.scenes, _uuid_token(tokens[1], path), "scene")
        scene.name = operation.value
        mutation.changed["scenes"].add(scene.id)
        mutation.changed_paths.append(path)
        return
    if len(tokens) == 3 and tokens[0] == "clips" and tokens[2] in _CLIP_FIELDS:
        clip = _entity(project.clips, _uuid_token(tokens[1], path), "clip")
        setattr(clip, tokens[2], operation.value)
        mutation.changed["clips"].add(clip.id)
        mutation.changed_paths.append(path)
        mutation.mark_impact(RuntimeImpact.REBUILD)
        return
    raise ApplicationError(
        f"Transaction path is not writable: {path}",
        code="unknown_path",
        path=path,
        status_code=422,
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
        cursor = 0
        while cursor < len(token):
            if token[cursor] != "~":
                decoded.append(token[cursor])
                cursor += 1
            elif cursor + 1 < len(token) and token[cursor + 1] in "01":
                decoded.append("~" if token[cursor + 1] == "0" else "/")
                cursor += 2
            else:
                raise ApplicationError(
                    f"Invalid JSON pointer escape in path: {path}",
                    code="invalid_path",
                    path=path,
                    status_code=422,
                )
        tokens.append("".join(decoded))
    return tokens


def _uuid_token(value: str, path: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as error:
        raise ApplicationError(
            f"Invalid entity ID in transaction path: {path}",
            code="invalid_path",
            path=path,
            status_code=422,
        ) from error


def _request_digest(request: TransactionRequest) -> str:
    payload = json.dumps(
        request.model_dump(
            mode="json",
            exclude={"allow_runtime_reset", "base_revision"},
        ),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _failure_result(
    request: TransactionRequest,
    current_revision: int,
    code: str,
    message: str,
) -> TransactionResult:
    return TransactionResult(
        ok=False,
        committed=False,
        base_revision=request.base_revision,
        before_revision=current_revision,
        after_revision=current_revision,
        current_revision=current_revision,
        errors=[ApiIssue(code=code, message=message)],
    )


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
