"""Deterministic VST3 candidate discovery and isolated metadata probing."""

from __future__ import annotations

import hashlib
import os
import tempfile
import time
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import ValidationError

from prism.plugins.errors import PluginConfigError, PluginWorkerError
from prism.plugins.types import PluginConfig, PluginRecord, PluginRegistryDocument

Probe = Callable[[Path], Iterable[dict[str, str]]]
_CHUNK_BYTES = 1024 * 1024


def discover_vst3(search_paths: Iterable[str]) -> tuple[Path, ...]:
    """Find VST3 files/bundles without descending into discovered bundles."""

    candidates: dict[str, Path] = {}
    for value in search_paths:
        root = Path(value).expanduser().resolve(strict=False)
        if not root.is_dir():
            continue
        for directory, names, files in os.walk(root):
            directory_path = Path(directory)
            bundles = [name for name in names if name.casefold().endswith(".vst3")]
            for name in bundles:
                candidate = (directory_path / name).resolve(strict=False)
                candidates[os.path.normcase(str(candidate))] = candidate
            names[:] = [name for name in names if name not in bundles]
            for name in files:
                if name.casefold().endswith(".vst3"):
                    candidate = (directory_path / name).resolve(strict=False)
                    candidates[os.path.normcase(str(candidate))] = candidate
    return tuple(candidates[key] for key in sorted(candidates))


def fingerprint_plugin_binary(path: Path | str) -> str:
    """Hash a VST3 file or bundle deterministically, including relative names."""

    candidate = Path(path).resolve(strict=True)
    digest = hashlib.sha256()
    if candidate.is_file():
        _update_file_digest(digest, candidate, candidate.name)
    elif candidate.is_dir():
        files = sorted(
            (item for item in candidate.rglob("*") if item.is_file()),
            key=lambda item: item.relative_to(candidate).as_posix().casefold(),
        )
        if not files:
            raise PluginConfigError(f"VST3 bundle contains no files: {candidate}")
        for item in files:
            _update_file_digest(digest, item, item.relative_to(candidate).as_posix())
    else:
        raise PluginConfigError(f"VST3 path is not a file or bundle: {candidate}")
    return digest.hexdigest()


def registry_id_for(path: Path, plugin_identifier: str) -> UUID:
    identity = f"prism:vst3:{os.path.normcase(str(path.resolve(strict=False)))}:{plugin_identifier}"
    return uuid5(NAMESPACE_URL, identity)


class PluginRegistry:
    """Build and persist a local registry while probing only exact trusted bytes."""

    def __init__(self, cache_path: Path | str) -> None:
        self.cache_path = Path(cache_path)

    def scan(self, config: PluginConfig, probe: Probe) -> PluginRegistryDocument:
        trust = {
            os.path.normcase(os.path.normpath(item.path)): item
            for item in config.trust
            if item.enabled
        }
        records: list[PluginRecord] = []
        for path in discover_vst3(config.search_paths):
            try:
                digest = fingerprint_plugin_binary(path)
            except (OSError, PluginConfigError) as error:
                records.append(_candidate_record(path, "0" * 64, error=str(error)))
                continue
            approval = trust.get(os.path.normcase(os.path.normpath(str(path))))
            trusted = approval is not None and approval.binary_sha256 == digest
            if not trusted:
                reason = "Plugin bytes are not allowlisted on this machine."
                if approval is not None:
                    reason = "Plugin bytes changed since they were allowlisted."
                records.append(_candidate_record(path, digest, error=reason))
                continue
            try:
                metadata = tuple(probe(path))
                if not metadata:
                    raise PluginWorkerError("Plugin host returned no VST3 entries")
                for item in metadata:
                    identifier = item.get("plugin_identifier") or item.get("name") or path.stem
                    category = item.get("category") or "Effect"
                    is_instrument = any(
                        marker in category.casefold() for marker in ("instrument", "synth")
                    )
                    records.append(
                        PluginRecord(
                            registry_id=registry_id_for(path, identifier),
                            path=str(path),
                            plugin_identifier=identifier,
                            binary_sha256=digest,
                            name=item.get("name") or path.stem,
                            manufacturer=item.get("manufacturer") or "Unknown",
                            version=item.get("version") or "Unknown",
                            category=category,
                            trusted=True,
                            available=not is_instrument,
                            error=(
                                "Plugin instruments are not supported in Phase 9."
                                if is_instrument
                                else None
                            ),
                        )
                    )
            except Exception as error:
                records.append(
                    _candidate_record(path, digest, trusted=True, error=str(error))
                )
        document = PluginRegistryDocument(
            scanned_at=time.time(),
            plugins=sorted(records, key=lambda item: (item.name.casefold(), item.path)),
        )
        self.save(document)
        return document

    def load(self) -> PluginRegistryDocument:
        if not self.cache_path.is_file():
            return PluginRegistryDocument(scanned_at=0.0)
        try:
            return PluginRegistryDocument.model_validate_json(
                self.cache_path.read_text(encoding="utf-8")
            )
        except (OSError, ValidationError) as error:
            raise PluginConfigError(
                f"Plugin registry cache is invalid: {self.cache_path}"
            ) from error

    def save(self, document: PluginRegistryDocument) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        handle, name = tempfile.mkstemp(
            prefix=f".{self.cache_path.name}.", suffix=".tmp", dir=self.cache_path.parent
        )
        os.close(handle)
        temporary = Path(name)
        try:
            payload = document.model_dump_json(indent=2).encode("utf-8") + b"\n"
            with temporary.open("wb") as output:
                output.write(payload)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, self.cache_path)
        except OSError as error:
            temporary.unlink(missing_ok=True)
            raise PluginConfigError(
                f"Could not save plugin registry cache: {self.cache_path}"
            ) from error

    def get(self, registry_id: UUID) -> PluginRecord | None:
        return next(
            (item for item in self.load().plugins if item.registry_id == registry_id),
            None,
        )


def _candidate_record(
    path: Path,
    digest: str,
    *,
    trusted: bool = False,
    error: str,
) -> PluginRecord:
    identifier = path.stem
    return PluginRecord(
        registry_id=registry_id_for(path, identifier),
        path=str(path),
        plugin_identifier=identifier,
        binary_sha256=digest,
        name=path.stem,
        trusted=trusted,
        available=False,
        error=error,
    )


def _update_file_digest(digest: Any, path: Path, relative_name: str) -> None:
    digest.update(relative_name.encode("utf-8"))
    digest.update(b"\0")
    with path.open("rb") as source:
        while chunk := source.read(_CHUNK_BYTES):
            digest.update(chunk)
    digest.update(b"\0")
