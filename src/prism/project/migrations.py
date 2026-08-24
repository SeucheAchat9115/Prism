"""Explicit project schema migrations."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from typing import Any

from prism.project.errors import MigrationError
from prism.project.models import CURRENT_SCHEMA_VERSION

Migration = Callable[[dict[str, Any]], dict[str, Any]]


class MigrationRegistry:
    """Registry for sequential, explicit JSON document migrations."""

    def __init__(self) -> None:
        self._migrations: dict[int, tuple[int, Migration]] = {}

    def register(self, from_version: int, to_version: int, migration: Migration) -> None:
        if from_version < 0 or to_version <= from_version:
            raise ValueError("Migration versions must increase from a non-negative source version")
        if from_version in self._migrations:
            raise ValueError(f"Migration from version {from_version} is already registered")
        self._migrations[from_version] = (to_version, migration)

    def migrate(
        self,
        document: dict[str, Any],
        *,
        from_version: int,
        target_version: int = CURRENT_SCHEMA_VERSION,
    ) -> dict[str, Any]:
        current = from_version
        migrated = deepcopy(document)
        while current < target_version:
            entry = self._migrations.get(current)
            if entry is None:
                raise MigrationError(f"No migration registered from schema version {current}")
            next_version, migration = entry
            if next_version <= current or next_version > target_version:
                raise MigrationError(
                    f"Invalid migration path from {current} to {next_version}"
                )
            try:
                migrated = migration(deepcopy(migrated))
            except Exception as exc:  # pragma: no cover - exact migration errors vary
                raise MigrationError(f"Migration {current}->{next_version} failed: {exc}") from exc
            if not isinstance(migrated, dict):
                raise MigrationError("A migration must return a JSON object")
            migrated["schema_version"] = next_version
            current = next_version
        return migrated


def _migrate_v1_to_v2(document: dict[str, Any]) -> dict[str, Any]:
    tracks = document.get("tracks", [])
    if not isinstance(tracks, list):
        raise MigrationError("Schema 1 tracks must be an array")
    for track in tracks:
        if not isinstance(track, dict):
            raise MigrationError("Schema 1 track entries must be objects")
        track.setdefault("effects", [])
    return document


DEFAULT_REGISTRY = MigrationRegistry()
DEFAULT_REGISTRY.register(1, 2, _migrate_v1_to_v2)
