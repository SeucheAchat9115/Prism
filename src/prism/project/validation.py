"""Cross-reference and Pydantic validation for project documents."""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum
from typing import Any

from pydantic import ValidationError

from prism.project.errors import ValidationIssue
from prism.project.models import Project


class ValidationReport:
    """A serializable collection of project validation issues."""

    def __init__(self, issues: Iterable[ValidationIssue] = ()) -> None:
        self.issues = tuple(issues)

    @property
    def ok(self) -> bool:
        return not self.issues

    def as_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "issues": [issue.as_dict() for issue in self.issues]}


class ValidationStage(StrEnum):
    ARCHIVE_INTEGRITY = "archive_integrity"
    SCHEMA = "schema"
    PROJECT_REFERENCES = "project_references"
    PLAYBACK_READINESS = "playback_readiness"
    PLUGIN_COMPATIBILITY = "plugin_compatibility"
    DEVICE_COMPATIBILITY = "device_compatibility"


class LayeredValidationReport:
    """Keep storage, schema, runtime, and device concerns independently visible."""

    def __init__(self, reports: dict[ValidationStage, Iterable[ValidationIssue]]) -> None:
        self.reports = {
            stage: tuple(reports.get(stage, ()))
            for stage in ValidationStage
        }

    @property
    def ok(self) -> bool:
        return all(not issues for issues in self.reports.values())

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "stages": {
                stage.value: {
                    "ok": not issues,
                    "issues": [issue.as_dict() for issue in issues],
                }
                for stage, issues in self.reports.items()
            },
        }


def _json_pointer(loc: tuple[Any, ...]) -> str:
    if not loc:
        return "/"
    escaped = (str(part).replace("~", "~0").replace("/", "~1") for part in loc)
    return "/" + "/".join(escaped)


def pydantic_issues(error: ValidationError) -> tuple[ValidationIssue, ...]:
    return tuple(
        ValidationIssue(
            code="invalid_field",
            path=_json_pointer(tuple(item["loc"])),
            message=item["msg"],
        )
        for item in error.errors()
    )


def project_reference_issues(project: Project) -> tuple[ValidationIssue, ...]:
    issues: list[ValidationIssue] = []

    def check_unique(values: list[Any], collection: str) -> set[Any]:
        seen: set[Any] = set()
        for index, value in enumerate(values):
            if value.id in seen:
                issues.append(
                    ValidationIssue(
                        code="duplicate_id",
                        path=f"/{collection}/{index}/id",
                        message=f"Duplicate {collection[:-1]} ID: {value.id}",
                    )
                )
            seen.add(value.id)
        return seen

    track_ids = check_unique(project.tracks, "tracks")
    scene_ids = check_unique(project.scenes, "scenes")
    clip_ids = check_unique(project.clips, "clips")
    asset_ids = check_unique(project.assets, "assets")
    slot_ids = check_unique(project.clip_slots, "clip_slots")

    plugin_ids: set[Any] = set()
    state_paths: set[str] = set()
    for track_index, track in enumerate(project.tracks):
        for effect_index, effect in enumerate(track.effects):
            path = f"/tracks/{track_index}/effects/{effect_index}"
            if effect.id in plugin_ids:
                issues.append(
                    ValidationIssue(
                        code="duplicate_id",
                        path=f"{path}/id",
                        message=f"Duplicate plugin instance ID: {effect.id}",
                    )
                )
            plugin_ids.add(effect.id)
            if effect.state is not None:
                if effect.state.member_path in state_paths:
                    issues.append(
                        ValidationIssue(
                            code="duplicate_plugin_state_member",
                            path=f"{path}/state/member_path",
                            message="Plugin state members must be unique per instance.",
                        )
                    )
                state_paths.add(effect.state.member_path)

    collections = {
        "tracks": track_ids,
        "scenes": scene_ids,
        "clips": clip_ids,
        "assets": asset_ids,
        "clip_slots": slot_ids,
        "plugin_instances": plugin_ids,
    }
    owners: dict[Any, str] = {}
    for collection, ids in collections.items():
        for entity_id in ids:
            previous = owners.get(entity_id)
            if previous is not None:
                issues.append(
                    ValidationIssue(
                        code="duplicate_id",
                        path=f"/{collection}",
                        message=(
                            f"Entity ID {entity_id} is shared by {previous} and {collection}."
                        ),
                    )
                )
            owners[entity_id] = collection

    for index, clip in enumerate(project.clips):
        if clip.asset_id not in asset_ids:
            issues.append(
                ValidationIssue(
                    code="missing_asset_reference",
                    path=f"/clips/{index}/asset_id",
                    message=f"Asset does not exist: {clip.asset_id}",
                )
            )

    occupied_slots: dict[tuple[Any, Any], int] = {}
    for index, slot in enumerate(project.clip_slots):
        if slot.track_id not in track_ids:
            issues.append(
                ValidationIssue(
                    code="missing_track_reference",
                    path=f"/clip_slots/{index}/track_id",
                    message=f"Track does not exist: {slot.track_id}",
                )
            )
        if slot.scene_id not in scene_ids:
            issues.append(
                ValidationIssue(
                    code="missing_scene_reference",
                    path=f"/clip_slots/{index}/scene_id",
                    message=f"Scene does not exist: {slot.scene_id}",
                )
            )
        if slot.clip_id is not None and slot.clip_id not in clip_ids:
            issues.append(
                ValidationIssue(
                    code="missing_clip_reference",
                    path=f"/clip_slots/{index}/clip_id",
                    message=f"Clip does not exist: {slot.clip_id}",
                )
            )
        key = (slot.track_id, slot.scene_id)
        if key in occupied_slots:
            issues.append(
                ValidationIssue(
                    code="duplicate_clip_slot",
                    path=f"/clip_slots/{index}",
                    message="Only one clip slot may occupy a track/scene pair.",
                )
            )
        occupied_slots[key] = index

    return tuple(issues)


def project_playback_issues(project: Project) -> tuple[ValidationIssue, ...]:
    """Validate ordering and source regions required by every runtime backend."""

    issues: list[ValidationIssue] = []
    assets = {asset.id: asset for asset in project.assets}
    for collection_name, entities in (("tracks", project.tracks), ("scenes", project.scenes)):
        orders = [entity.order for entity in entities]
        if sorted(orders) != list(range(len(entities))):
            issues.append(
                ValidationIssue(
                    code="invalid_ordering",
                    path=f"/{collection_name}",
                    message=f"{collection_name.title()} must have unique contiguous order values.",
                )
            )

    for index, asset in enumerate(project.assets):
        if asset.channels not in (1, 2):
            issues.append(
                ValidationIssue(
                    code="unsupported_channel_layout",
                    path=f"/assets/{index}/channels",
                    message="Playback supports only mono or stereo audio assets.",
                )
            )
        if asset.frames <= 0:
            issues.append(
                ValidationIssue(
                    code="empty_audio_asset",
                    path=f"/assets/{index}/frames",
                    message="Playback requires an audio asset with at least one frame.",
                )
            )
        if asset.format.upper() not in {"WAV", "AIFF"}:
            issues.append(
                ValidationIssue(
                    code="unsupported_audio_format",
                    path=f"/assets/{index}/format",
                    message=f"Unsupported audio format: {asset.format}",
                )
            )

    for index, clip in enumerate(project.clips):
        clip_asset = assets.get(clip.asset_id)
        if clip_asset is None:
            continue
        if clip.source_offset_frames >= clip_asset.frames:
            issues.append(
                ValidationIssue(
                    code="clip_region_out_of_bounds",
                    path=f"/clips/{index}/source_offset_frames",
                    message="Clip source offset must be before the end of its audio asset.",
                )
            )
        if (
            not clip.loop
            and clip.duration_frames is not None
            and clip.source_offset_frames + clip.duration_frames > clip_asset.frames
        ):
            issues.append(
                ValidationIssue(
                    code="clip_region_out_of_bounds",
                    path=f"/clips/{index}/duration_frames",
                    message="A non-looping clip region must fit inside its audio asset.",
                )
            )
    return tuple(issues)
