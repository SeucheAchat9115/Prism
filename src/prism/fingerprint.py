"""Portable project identity, render cache keys, and schema migrations."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import platform
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Mapping

from prism.errors import ProjectError
from prism.plugins import LEGACY_AUTOMATION_VERSION
from prism.timing import LEGACY_TIMING_VERSION
from prism.version import __version__
from prism.vst import hash_vst3

if TYPE_CHECKING:
    from prism.project.builder import Project
    from prism.render import ExportProfile, StemDeliveryMode


PROJECT_CONFIGURATION_SCHEMA_VERSION = 11
RENDER_MANIFEST_SCHEMA_VERSION = 2
FINGERPRINT_SCHEMA_VERSION = 1
NATIVE_DSP_VERSION = "1"
_CACHE_DIRECTORY = ".prism-cache"
_CACHE_FILENAME = "fingerprints.json"


@dataclass(frozen=True, slots=True)
class FingerprintedFile:
    """A project-relative content identity without machine-specific paths."""

    path: str
    kind: str
    sha256: str
    size: int

    def as_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "kind": self.kind,
            "sha256": self.sha256,
            "size": self.size,
        }


@dataclass(frozen=True, slots=True)
class ProjectFingerprint:
    """The portable project identity plus the environment-specific render key."""

    schema_version: int
    project_schema_version: int
    requested_project_version: str
    runtime_prism_version: str
    portable_sha256: str
    render_key: str
    configuration: Mapping[str, object]
    script: FingerprintedFile
    source_audio: tuple[FingerprintedFile, ...]
    plugin_states: tuple[FingerprintedFile, ...]
    plugin_presets: tuple[FingerprintedFile, ...]
    vst_binaries: tuple[Mapping[str, object], ...]
    seeds: tuple[Mapping[str, object], ...]
    runtime: Mapping[str, object]
    backend: Mapping[str, object]
    render_settings: Mapping[str, object]
    stem_routing: str | None
    deterministic: bool
    external_backend: Mapping[str, object]

    @property
    def sha256(self) -> str:
        """Return the portable identity hash used by cache consumers."""

        return self.portable_sha256

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-safe fingerprint suitable for a render manifest."""

        return {
            "schema_version": self.schema_version,
            "project_schema_version": self.project_schema_version,
            "requested_project_version": self.requested_project_version,
            "runtime_prism_version": self.runtime_prism_version,
            "portable_sha256": self.portable_sha256,
            "render_key": self.render_key,
            "configuration": _json_safe(self.configuration),
            "script": self.script.as_dict(),
            "source_audio": [item.as_dict() for item in self.source_audio],
            "plugin_states": [item.as_dict() for item in self.plugin_states],
            "plugin_presets": [item.as_dict() for item in self.plugin_presets],
            "vst_binaries": [_json_safe(item) for item in self.vst_binaries],
            "seeds": [_json_safe(item) for item in self.seeds],
            "runtime": _json_safe(self.runtime),
            "backend": _json_safe(self.backend),
            "render_settings": _json_safe(self.render_settings),
            "stem_routing": self.stem_routing,
            "deterministic": self.deterministic,
            "external_backend": _json_safe(self.external_backend),
        }


def fingerprint_project(
    project: Project,
    *,
    profile: ExportProfile | None = None,
    stem_mode: StemDeliveryMode | None = None,
) -> ProjectFingerprint:
    """Build a portable identity and a runtime-aware render key for a project."""

    if stem_mode is not None and stem_mode not in {"channel_taps", "master_inputs"}:
        raise ProjectError(
            "Stem delivery mode must be 'channel_taps' or 'master_inputs', or None."
        )
    project.validate(verify_vst=False)
    configuration = migrate_project_configuration(
        project.configuration(verify_vst=False)
    )
    cache = _FingerprintCache(project.root)
    script = _fingerprint_file(cache, project.root, project.script, "script", "script")

    source_audio = tuple(
        sorted(
            (
                _fingerprint_file(
                    cache,
                    project.root,
                    path,
                    f"source:{_relative(project.root, path)}",
                    "source_audio",
                )
                for path in project._sample_files()
            ),
            key=lambda item: item.path.casefold(),
        )
    )

    plugin_states: dict[str, FingerprintedFile] = {}
    plugin_presets: dict[str, FingerprintedFile] = {}
    vst_binaries: dict[tuple[str, str], Mapping[str, object]] = {}
    for plugin in project._external_plugins():
        assert plugin.vst3 is not None
        path, entry = project.vsts.resolve(plugin.vst3.alias, verify=False)
        binary_key = (entry.alias, entry.platform)
        if binary_key not in vst_binaries:
            binary = _fingerprint_bundle(
                cache,
                path,
                f"vst:{entry.alias}:{entry.platform}",
            )
            if binary.sha256 != entry.sha256:
                raise ProjectError(
                    f"Registered VST3 {entry.alias!r} has changed. Re-add it to accept "
                    "the new file."
                )
            vst_binaries[binary_key] = {
                "alias": entry.alias,
                "platform": entry.platform,
                "sha256": binary.sha256,
            }
        for relative, target, collection, label in (
            (plugin.vst3.state, plugin_states, "state", "plugin state"),
            (plugin.vst3.preset, plugin_presets, "preset", "plugin preset"),
        ):
            if relative is None:
                continue
            asset = project.root / relative
            if not asset.is_file() or asset.is_symlink():
                raise ProjectError(
                    f"Fingerprint {label} is missing or unsafe: {relative}."
                )
            target[relative] = _fingerprint_file(
                cache,
                project.root,
                asset,
                f"{collection}:{relative}",
                f"plugin_{collection}",
            )

    states = tuple(sorted(plugin_states.values(), key=lambda item: item.path.casefold()))
    presets = tuple(sorted(plugin_presets.values(), key=lambda item: item.path.casefold()))
    binary_values = tuple(
        vst_binaries[key] for key in sorted(vst_binaries, key=lambda item: (item[0], item[1]))
    )
    seeds = tuple(_seed_values(configuration))
    runtime = _runtime_metadata()
    has_external_backend = bool(binary_values)
    external_backend: dict[str, object]
    if has_external_backend:
        external_backend = {
            "name": "dawdreamer",
            "version": runtime["dawdreamer"],
            "determinism": "conditional_external",
        }
    else:
        external_backend = {
            "name": "prism-native",
            "version": NATIVE_DSP_VERSION,
            "determinism": "deterministic",
        }
    backend: dict[str, object] = {
        "configured": project.vst_backend.as_dict(),
        "dsp": {"name": "prism-native", "version": NATIVE_DSP_VERSION},
        "external": external_backend,
    }
    render_settings: dict[str, object] = {
        "internal_sample_rate": project.sample_rate,
        "delivery_profile": (
            None
            if profile is None
            else profile.as_dict(
                resolved_sample_rate=(
                    project.sample_rate
                    if profile.delivery_sample_rate is None
                    else profile.delivery_sample_rate
                )
            )
        ),
        "stem_mode": stem_mode,
    }
    portable_payload = {
        "schema_version": FINGERPRINT_SCHEMA_VERSION,
        "project_schema_version": configuration["schema_version"],
        "requested_project_version": project.prism_version,
        "configuration": configuration,
        "script": script.as_dict(),
        "source_audio": [item.as_dict() for item in source_audio],
        "plugin_states": [item.as_dict() for item in states],
        "plugin_presets": [item.as_dict() for item in presets],
        "vst_binaries": binary_values,
        "seeds": seeds,
        "render_settings": render_settings,
        "stem_routing": stem_mode,
    }
    portable_sha256 = _sha256_json(portable_payload)
    render_payload = {
        "portable_sha256": portable_sha256,
        "runtime": runtime,
        "backend": backend,
    }
    render_key = _sha256_json(render_payload)
    cache.save()
    schema_version = configuration.get("schema_version")
    if not isinstance(schema_version, int) or isinstance(schema_version, bool):
        raise ProjectError("Migrated project configuration has an invalid schema version.")
    return ProjectFingerprint(
        schema_version=FINGERPRINT_SCHEMA_VERSION,
        project_schema_version=schema_version,
        requested_project_version=project.prism_version,
        runtime_prism_version=__version__,
        portable_sha256=portable_sha256,
        render_key=render_key,
        configuration=configuration,
        script=script,
        source_audio=source_audio,
        plugin_states=states,
        plugin_presets=presets,
        vst_binaries=binary_values,
        seeds=seeds,
        runtime=runtime,
        backend=backend,
        render_settings=render_settings,
        stem_routing=stem_mode,
        deterministic=not has_external_backend,
        external_backend=external_backend,
    )


def migrate_project_configuration(
    configuration: Mapping[str, object],
) -> dict[str, object]:
    """Migrate supported pre-task schemas without inferring from a version label."""

    raw_schema = configuration.get("schema_version", 0)
    if isinstance(raw_schema, bool) or not isinstance(raw_schema, int):
        raise ProjectError("Project configuration has an invalid schema version.")
    if raw_schema > PROJECT_CONFIGURATION_SCHEMA_VERSION:
        raise ProjectError(
            "Project configuration schema "
            f"{raw_schema} is newer than the supported {PROJECT_CONFIGURATION_SCHEMA_VERSION}."
        )
    migrated = dict(configuration)
    if raw_schema < PROJECT_CONFIGURATION_SCHEMA_VERSION:
        migrated.setdefault("timing_compatibility", LEGACY_TIMING_VERSION)
        migrated.setdefault("automation_compatibility", LEGACY_AUTOMATION_VERSION)
        migrated.setdefault("audio_release_policy", "legacy")
        migrated.setdefault("controller_boundary", "legacy")
        migrated["migrated_from_schema_version"] = raw_schema
        migrated["schema_version"] = PROJECT_CONFIGURATION_SCHEMA_VERSION
    return migrated


def migrate_render_manifest(manifest: Mapping[str, object]) -> dict[str, object]:
    """Accept the task-01/12 manifest and migrate it to the current schema."""

    raw_schema = manifest.get("schema_version")
    if isinstance(raw_schema, bool) or not isinstance(raw_schema, int):
        raise ProjectError("Stem ownership manifest has an invalid schema version.")
    if raw_schema > RENDER_MANIFEST_SCHEMA_VERSION:
        raise ProjectError(
            "Stem ownership manifest schema "
            f"{raw_schema} is newer than the supported {RENDER_MANIFEST_SCHEMA_VERSION}."
        )
    if raw_schema not in {1, RENDER_MANIFEST_SCHEMA_VERSION}:
        raise ProjectError("Stem ownership manifest has an unsupported schema.")
    migrated = dict(manifest)
    if raw_schema == 1:
        migrated["schema_version"] = RENDER_MANIFEST_SCHEMA_VERSION
        migrated.setdefault("export_profile", {})
        migrated.setdefault("delivery", {})
        migrated.setdefault("master_processing", {})
        migrated.setdefault("fingerprint", {})
    return migrated


class _FingerprintCache:
    """A JSON-only cache invalidated by safe filesystem change signatures."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve(strict=False)
        self.directory = self.root / _CACHE_DIRECTORY
        self.path = self.directory / _CACHE_FILENAME
        self.entries: dict[str, dict[str, object]] = {}
        self.dirty = False
        if self.directory.is_symlink() or self.path.is_symlink():
            raise ProjectError("Fingerprint cache cannot contain symlinks.")
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ProjectError(f"Could not read fingerprint cache: {error}") from error
        if not isinstance(raw, dict) or raw.get("schema_version") != FINGERPRINT_SCHEMA_VERSION:
            self.dirty = True
            return
        entries = raw.get("entries", {})
        if isinstance(entries, dict):
            self.entries = {
                str(key): value for key, value in entries.items() if isinstance(value, dict)
            }

    def digest_file(self, path: Path, key: str, kind: str) -> FingerprintedFile:
        _require_file(path, kind)
        signature = _file_signature(path)
        cached = self.entries.get(key)
        if _cache_matches(cached, signature, kind):
            assert cached is not None
            cached_sha256 = cached.get("sha256")
            assert isinstance(cached_sha256, str)
            sha256 = cached_sha256
        else:
            sha256 = _hash_file(path)
            after = _file_signature(path)
            if after != signature:
                sha256 = _hash_file(path)
                signature = _file_signature(path)
            self.entries[key] = {
                "kind": kind,
                "signature": signature,
                "sha256": sha256,
            }
            self.dirty = True
        return FingerprintedFile(
            path=_relative(self.root, path),
            kind=kind,
            sha256=str(sha256),
            size=path.stat().st_size,
        )

    def digest_bundle(self, path: Path, key: str) -> FingerprintedFile:
        if path.is_symlink() or not path.exists():
            raise ProjectError(f"VST3 path is not a safe file or bundle: {path}")
        if path.is_file():
            signature = _file_signature(path)
            cached = self.entries.get(key)
            if _cache_matches(cached, signature, "vst_binary"):
                assert cached is not None
                cached_sha256 = cached.get("sha256")
                assert isinstance(cached_sha256, str)
                sha256 = cached_sha256
            else:
                sha256 = _hash_file(path)
                after = _file_signature(path)
                if after != signature:
                    sha256 = _hash_file(path)
                    signature = _file_signature(path)
                self.entries[key] = {
                    "kind": "vst_binary",
                    "signature": signature,
                    "sha256": sha256,
                }
                self.dirty = True
            return FingerprintedFile(
                path=key,
                kind="vst_binary",
                sha256=str(sha256),
                size=path.stat().st_size,
            )
        if not path.is_dir():
            raise ProjectError(f"VST3 path is not a safe file or bundle: {path}")
        members = _bundle_signature(path)
        cached = self.entries.get(key)
        if _cache_matches(cached, members, "vst_binary"):
            assert cached is not None
            cached_sha256 = cached.get("sha256")
            assert isinstance(cached_sha256, str)
            sha256 = cached_sha256
        else:
            sha256 = hash_vst3(path)
            after_members = _bundle_signature(path)
            if after_members != members:
                sha256 = hash_vst3(path)
                members = _bundle_signature(path)
            self.entries[key] = {
                "kind": "vst_binary",
                "signature": members,
                "sha256": sha256,
            }
            self.dirty = True
        size = sum(_member_size(member) for member in members)
        return FingerprintedFile(
            path=key,
            kind="vst_binary",
            sha256=str(sha256),
            size=size,
        )

    def save(self) -> None:
        if not self.dirty:
            return
        if self.directory.is_symlink():
            raise ProjectError("Fingerprint cache cannot contain symlinks.")
        self.directory.mkdir(parents=True, exist_ok=True)
        if self.path.is_symlink():
            raise ProjectError("Fingerprint cache cannot contain symlinks.")
        temporary = self.directory / f".{_CACHE_FILENAME}.{uuid.uuid4().hex}.tmp"
        data = {"schema_version": FINGERPRINT_SCHEMA_VERSION, "entries": self.entries}
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as stream:
                json.dump(data, stream, indent=2, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)


def _fingerprint_file(
    cache: _FingerprintCache,
    root: Path,
    path: Path,
    key: str,
    kind: str,
) -> FingerprintedFile:
    _relative(root, path)
    return cache.digest_file(path, key, kind)


def _fingerprint_bundle(
    cache: _FingerprintCache,
    path: Path,
    key: str,
) -> FingerprintedFile:
    return cache.digest_bundle(path, key)


def _relative(root: Path, path: Path) -> str:
    resolved_root = root.resolve(strict=False)
    resolved = path.resolve(strict=False)
    try:
        return resolved.relative_to(resolved_root).as_posix()
    except ValueError as error:
        raise ProjectError(
            f"Fingerprint asset must be inside the project folder: {path}"
        ) from error


def _require_file(path: Path, kind: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise ProjectError(f"Fingerprint {kind} is missing or unsafe: {path}")


def _file_signature(path: Path) -> dict[str, object]:
    stat = path.stat()
    return {
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "ctime_ns": stat.st_ctime_ns,
        "inode": getattr(stat, "st_ino", 0),
    }


def _bundle_signature(path: Path) -> list[dict[str, object]]:
    members: list[dict[str, object]] = []
    for child in sorted(path.rglob("*"), key=lambda item: item.relative_to(path).as_posix()):
        if child.is_symlink():
            raise ProjectError(f"VST3 bundle cannot contain symlinks: {child}")
        if child.is_file():
            stat = child.stat()
            members.append(
                {
                    "path": child.relative_to(path).as_posix(),
                    "size": stat.st_size,
                    "mtime_ns": stat.st_mtime_ns,
                    "ctime_ns": stat.st_ctime_ns,
                    "inode": getattr(stat, "st_ino", 0),
                }
            )
    if not members:
        raise ProjectError(f"VST3 bundle is empty: {path}")
    return members


def _cache_matches(
    cached: Mapping[str, object] | None,
    signature: object,
    kind: str,
) -> bool:
    if cached is None or cached.get("kind") != kind or cached.get("signature") != signature:
        return False
    sha256 = cached.get("sha256")
    return isinstance(sha256, str) and len(sha256) == 64


def _member_size(member: Mapping[str, object]) -> int:
    value = member.get("size")
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_json(value: object) -> str:
    payload = json.dumps(
        _json_safe(value),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _json_safe(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, Path):
        return value.as_posix()
    return value


def _seed_values(configuration: Mapping[str, object]) -> list[Mapping[str, object]]:
    found: list[Mapping[str, object]] = []

    def visit(value: object, path: str) -> None:
        if isinstance(value, Mapping):
            for key in sorted(value, key=str):
                child_path = f"{path}.{key}" if path else str(key)
                visit(value[key], child_path)
        elif isinstance(value, (list, tuple)):
            for index, item in enumerate(value):
                visit(item, f"{path}[{index}]")
        elif path.rsplit(".", 1)[-1].casefold() in {"seed", "noise_seed", "humanize_seed"}:
            found.append({"path": path, "value": _json_safe(value)})

    visit(configuration, "")
    return found


def _distribution_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _runtime_metadata() -> dict[str, object]:
    return {
        "prism": __version__,
        "python": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "platform": sys.platform,
        "numpy": _distribution_version("numpy"),
        "soundfile": _distribution_version("soundfile"),
        "soxr": _distribution_version("soxr"),
        "dawdreamer": _distribution_version("dawdreamer"),
    }


__all__ = [
    "FINGERPRINT_SCHEMA_VERSION",
    "FingerprintedFile",
    "NATIVE_DSP_VERSION",
    "PROJECT_CONFIGURATION_SCHEMA_VERSION",
    "ProjectFingerprint",
    "RENDER_MANIFEST_SCHEMA_VERSION",
    "fingerprint_project",
    "migrate_project_configuration",
    "migrate_render_manifest",
]
