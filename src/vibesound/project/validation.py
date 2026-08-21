"""Cross-reference and Pydantic validation for project documents."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from pydantic import ValidationError

from vibesound.project.errors import ValidationIssue
from vibesound.project.models import Project


class ValidationReport:
    """A serializable collection of project validation issues."""

    def __init__(self, issues: Iterable[ValidationIssue] = ()) -> None:
        self.issues = tuple(issues)

    @property
    def ok(self) -> bool:
        return not self.issues

    def as_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "issues": [issue.as_dict() for issue in self.issues]}


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

    del slot_ids

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
