"""Project-local VST3 declarations and registry management."""

from __future__ import annotations

import hashlib
import json
import os
import platform as system_platform
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath, PureWindowsPath
from types import MappingProxyType
from typing import Any, Mapping

from prism.errors import ProjectError

REGISTRY_FILENAME = "vst.json"
REGISTRY_SCHEMA_VERSION = 1
_ALIAS = re.compile(r"[a-z0-9][a-z0-9_-]*")


@dataclass(frozen=True, slots=True)
class VST3:
    """A reproducible VST3 instance configured from a project's registry."""

    alias: str
    state: str | None = None
    preset: str | None = None
    parameters: Mapping[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        alias = normalize_alias(self.alias)
        if self.state is not None and self.preset is not None:
            raise ProjectError("Choose either a VST state file or a preset file, not both.")
        state = _safe_project_file(self.state, "VST state")
        preset = _safe_project_file(self.preset, "VST preset")
        values: dict[str, float] = {}
        for name, value in self.parameters.items():
            clean = str(name).strip()
            if not clean:
                raise ProjectError("VST parameter names cannot be empty.")
            resolved = float(value)
            if not 0.0 <= resolved <= 1.0:
                raise ProjectError(
                    f"VST parameter {clean!r} must be a normalized value between 0 and 1."
                )
            values[clean] = resolved
        object.__setattr__(self, "alias", alias)
        object.__setattr__(self, "state", state)
        object.__setattr__(self, "preset", preset)
        object.__setattr__(self, "parameters", MappingProxyType(values))


@dataclass(frozen=True, slots=True)
class VSTRegistryEntry:
    """One platform-specific VST3 binary recorded in ``vst.json``."""

    alias: str
    platform: str
    path: str
    sha256: str


class VSTRegistry:
    """Read and update the explicit VST3 registry inside one Prism project."""

    def __init__(self, project: str | Path) -> None:
        requested = Path(project).resolve(strict=False)
        self.root = requested.parent if requested.name.casefold() == "main.py" else requested
        self.path = self.root / REGISTRY_FILENAME

    def initialize(self) -> None:
        """Create an empty registry when the project does not have one yet."""

        if not self.path.exists():
            self._write({"schema_version": REGISTRY_SCHEMA_VERSION, "plugins": {}})

    def entries(self, *, platform: str | None = None) -> tuple[VSTRegistryEntry, ...]:
        data = self._read()
        selected = platform or platform_key()
        entries: list[VSTRegistryEntry] = []
        for alias, platforms in sorted(data["plugins"].items()):
            if platform is None:
                record = platforms.get(selected)
                if record is not None:
                    entries.append(_entry(alias, selected, record))
            else:
                record = platforms.get(platform)
                if record is not None:
                    entries.append(_entry(alias, platform, record))
        return tuple(entries)

    def all_entries(self) -> tuple[VSTRegistryEntry, ...]:
        data = self._read()
        return tuple(
            _entry(alias, platform, record)
            for alias, platforms in sorted(data["plugins"].items())
            for platform, record in sorted(platforms.items())
        )

    def add(
        self,
        alias: str,
        plugin_path: str | Path,
        *,
        replace: bool = False,
        platform: str | None = None,
    ) -> VSTRegistryEntry:
        clean = normalize_alias(alias)
        selected = platform or platform_key()
        source = Path(plugin_path).expanduser().resolve(strict=True)
        if source.suffix.casefold() != ".vst3":
            raise ProjectError("A registered plugin must be a .vst3 file or bundle.")
        data = self._read(create=True)
        platforms = data["plugins"].setdefault(clean, {})
        if selected in platforms and not replace:
            raise ProjectError(
                f"VST alias {clean!r} is already registered for {selected}; use --replace."
            )
        stored_path = _portable_path(source, self.root)
        record = {"path": stored_path, "sha256": hash_vst3(source)}
        platforms[selected] = record
        self._write(data)
        return _entry(clean, selected, record)

    def remove(
        self,
        alias: str,
        *,
        all_platforms: bool = False,
        platform: str | None = None,
    ) -> None:
        clean = normalize_alias(alias)
        selected = platform or platform_key()
        data = self._read()
        platforms = data["plugins"].get(clean)
        if platforms is None:
            raise ProjectError(f"VST alias {clean!r} is not registered.")
        if all_platforms:
            del data["plugins"][clean]
        else:
            if selected not in platforms:
                raise ProjectError(f"VST alias {clean!r} is not registered for {selected}.")
            del platforms[selected]
            if not platforms:
                del data["plugins"][clean]
        self._write(data)

    def resolve(self, alias: str, *, verify: bool = True) -> tuple[Path, VSTRegistryEntry]:
        clean = normalize_alias(alias)
        selected = platform_key()
        data = self._read()
        try:
            record = data["plugins"][clean][selected]
        except KeyError as error:
            raise ProjectError(
                f"VST alias {clean!r} is not registered for {selected} in {self.path.name}."
            ) from error
        entry = _entry(clean, selected, record)
        candidate = Path(entry.path)
        path = candidate if candidate.is_absolute() else self.root / candidate
        path = path.resolve(strict=False)
        if not path.exists():
            raise ProjectError(f"Registered VST3 does not exist: {path}")
        if verify:
            current = hash_vst3(path)
            if current != entry.sha256:
                raise ProjectError(
                    f"Registered VST3 {clean!r} has changed. Re-add it to accept the new file."
                )
        return path, entry

    def _read(self, *, create: bool = False) -> dict[str, Any]:
        if not self.path.exists():
            if create:
                return {"schema_version": REGISTRY_SCHEMA_VERSION, "plugins": {}}
            raise ProjectError(
                f"Missing {REGISTRY_FILENAME} in {self.root}. Create it with prism create "
                "or register a plugin with prism plugins add."
            )
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ProjectError(f"Could not read {self.path}: {error}") from error
        if not isinstance(data, dict) or data.get("schema_version") != REGISTRY_SCHEMA_VERSION:
            raise ProjectError(f"{REGISTRY_FILENAME} has an unsupported schema version.")
        plugins = data.get("plugins")
        if not isinstance(plugins, dict):
            raise ProjectError(f"{REGISTRY_FILENAME} must contain a plugins object.")
        return data

    def _write(self, data: Mapping[str, object]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
        )
        os.replace(temporary, self.path)


def platform_key() -> str:
    """Return the supported registry key for this operating system."""

    current: str = sys.platform
    if current == "win32":
        return "windows"
    if current.startswith("linux"):
        if "microsoft" in system_platform.release().casefold():
            raise ProjectError(
                "Prism VST3 hosting needs native Linux and is not supported in WSL."
            )
        return "linux"
    raise ProjectError("Prism VST3 hosting currently supports Windows and native Linux only.")


def normalize_alias(alias: str) -> str:
    clean = alias.strip().casefold()
    if _ALIAS.fullmatch(clean) is None:
        raise ProjectError(
            "VST aliases use lowercase letters, numbers, hyphens, and underscores only."
        )
    return clean


def hash_vst3(path: Path) -> str:
    """Hash a VST3 file or bundle, including relative filenames for bundles."""

    digest = hashlib.sha256()
    if path.is_file():
        _hash_file(digest, path)
        return digest.hexdigest()
    if not path.is_dir():
        raise ProjectError(f"VST3 path is not a file or bundle: {path}")
    files = sorted(item for item in path.rglob("*") if item.is_file())
    if not files:
        raise ProjectError(f"VST3 bundle is empty: {path}")
    for item in files:
        relative = item.relative_to(path).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        _hash_file(digest, item)
    return digest.hexdigest()


def _hash_file(digest: object, path: Path) -> None:
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)  # type: ignore[attr-defined]


def _entry(alias: str, platform: str, record: object) -> VSTRegistryEntry:
    if not isinstance(record, dict):
        raise ProjectError(f"Invalid {REGISTRY_FILENAME} entry for {alias!r}.")
    path = record.get("path")
    sha256 = record.get("sha256")
    if not isinstance(path, str) or not isinstance(sha256, str) or len(sha256) != 64:
        raise ProjectError(f"Invalid {REGISTRY_FILENAME} entry for {alias!r}.")
    return VSTRegistryEntry(alias, platform, path, sha256)


def _portable_path(source: Path, root: Path) -> str:
    try:
        return source.relative_to(root.resolve(strict=False)).as_posix()
    except ValueError:
        return source.as_posix()


def _safe_project_file(value: str | None, label: str) -> str | None:
    if value is None:
        return None
    clean = value.strip()
    posix = PurePosixPath(clean)
    windows = PureWindowsPath(clean)
    unsafe = (
        not clean
        or posix.is_absolute()
        or windows.is_absolute()
        or bool(windows.drive)
        or ".." in posix.parts
    )
    if unsafe:
        raise ProjectError(f"{label} must be a relative path inside the project folder.")
    return posix.as_posix()


__all__ = ["VST3", "VSTRegistry", "VSTRegistryEntry", "hash_vst3", "platform_key"]
