"""Atomic machine-local configuration for VST3 search paths and trust."""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

from pydantic import ValidationError

from prism.plugins.errors import PluginConfigError
from prism.plugins.registry import fingerprint_plugin_binary
from prism.plugins.types import PluginConfig, PluginTrustRecord

_CONFIG_ENV = "PRISM_PLUGIN_CONFIG"


def default_config_path() -> Path:
    """Return the per-user plugin policy path, with an override for tests/agents."""

    override = os.environ.get(_CONFIG_ENV)
    if override:
        return Path(override).expanduser().resolve(strict=False)
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "Prism" / "plugins.json"


class PluginConfigStore:
    """Read and mutate the explicit local trust boundary."""

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path is not None else default_config_path()

    @property
    def registry_path(self) -> Path:
        return self.path.with_name("plugin-registry.json")

    def load(self) -> PluginConfig:
        if not self.path.is_file():
            return PluginConfig()
        try:
            return PluginConfig.model_validate_json(self.path.read_text(encoding="utf-8"))
        except (OSError, ValidationError) as error:
            raise PluginConfigError(f"Plugin configuration is invalid: {self.path}") from error

    def save(self, config: PluginConfig) -> PluginConfig:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = config.model_dump_json(indent=2).encode("utf-8") + b"\n"
        handle, name = tempfile.mkstemp(
            prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent
        )
        os.close(handle)
        temporary = Path(name)
        try:
            with temporary.open("wb") as output:
                output.write(payload)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, self.path)
        except OSError as error:
            temporary.unlink(missing_ok=True)
            raise PluginConfigError(f"Could not save plugin configuration: {self.path}") from error
        return config.model_copy(deep=True)

    def add_search_path(self, path: Path | str) -> PluginConfig:
        resolved = str(Path(path).expanduser().resolve(strict=True))
        if not Path(resolved).is_dir():
            raise PluginConfigError(f"Plugin search path is not a directory: {resolved}")
        config = self.load()
        existing = {_path_key(value) for value in config.search_paths}
        if _path_key(resolved) not in existing:
            config.search_paths.append(resolved)
            config.search_paths.sort(key=_path_key)
        return self.save(config)

    def remove_search_path(self, path: Path | str) -> PluginConfig:
        key = _path_key(str(Path(path).expanduser().resolve(strict=False)))
        config = self.load()
        config.search_paths = [value for value in config.search_paths if _path_key(value) != key]
        return self.save(config)

    def trust_plugin(self, path: Path | str) -> PluginTrustRecord:
        resolved = Path(path).expanduser().resolve(strict=True)
        if resolved.suffix.casefold() != ".vst3":
            raise PluginConfigError(f"Only VST3 bundles can be trusted: {resolved}")
        record = PluginTrustRecord(
            path=str(resolved),
            binary_sha256=fingerprint_plugin_binary(resolved),
            trusted_at=time.time(),
        )
        config = self.load()
        key = _path_key(record.path)
        config.trust = [item for item in config.trust if _path_key(item.path) != key]
        config.trust.append(record)
        config.trust.sort(key=lambda item: _path_key(item.path))
        self.save(config)
        return record

    def revoke_plugin(self, path: Path | str) -> PluginConfig:
        key = _path_key(str(Path(path).expanduser().resolve(strict=False)))
        config = self.load()
        config.trust = [item for item in config.trust if _path_key(item.path) != key]
        return self.save(config)


def matching_trust(
    config: PluginConfig,
    path: Path,
    binary_sha256: str,
) -> PluginTrustRecord | None:
    key = _path_key(str(path.resolve(strict=False)))
    return next(
        (
            record
            for record in config.trust
            if record.enabled
            and _path_key(record.path) == key
            and record.binary_sha256 == binary_sha256
        ),
        None,
    )


def _path_key(value: str) -> str:
    return os.path.normcase(os.path.normpath(value))
