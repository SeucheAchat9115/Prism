"""High-level trust enforcement and control for one interactive plugin worker."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from prism.plugins.client import PluginWorkerClient
from prism.plugins.config import PluginConfigStore, matching_trust
from prism.plugins.errors import PluginConfigError, PluginTrustError, PluginUnavailableError
from prism.plugins.registry import PluginRegistry, fingerprint_plugin_binary
from prism.plugins.types import (
    PluginCompatibility,
    PluginParameter,
    PluginRecord,
    PluginRegistryDocument,
    PluginTrustRecord,
    PluginWorkerStatus,
)
from prism.project.models import PluginInstance, Project


class PluginManager:
    """Coordinate local policy, cached discovery, and an isolated interactive host."""

    def __init__(
        self,
        store: PluginConfigStore | None = None,
        worker: PluginWorkerClient | None = None,
    ) -> None:
        self.store = store or PluginConfigStore()
        self.registry = PluginRegistry(self.store.registry_path)
        self.worker = worker or PluginWorkerClient()
        self._loaded: set[UUID] = set()

    def scan(self) -> PluginRegistryDocument:
        config = self.store.load()
        return self.registry.scan(config, self.worker.probe)

    def list_plugins(self) -> PluginRegistryDocument:
        return self.registry.load()

    def add_search_path(self, path: Path | str) -> list[str]:
        return self.store.add_search_path(path).search_paths

    def remove_search_path(self, path: Path | str) -> list[str]:
        return self.store.remove_search_path(path).search_paths

    def trust(self, path: Path | str) -> PluginTrustRecord:
        return self.store.trust_plugin(path)

    def revoke(self, path: Path | str) -> None:
        self.store.revoke_plugin(path)

    def status(self) -> PluginWorkerStatus:
        return self.worker.status()

    def is_loaded(self, instance_id: UUID) -> bool:
        return instance_id in self._loaded

    def restart(self) -> PluginWorkerStatus:
        self._loaded.clear()
        return self.worker.restart()

    def require_record(self, registry_id: UUID) -> PluginRecord:
        record = self.registry.get(registry_id)
        if record is None:
            raise PluginUnavailableError(
                f"Plugin registry entry does not exist; scan first: {registry_id}"
            )
        if not record.available:
            raise PluginUnavailableError(record.error or f"Plugin is unavailable: {record.name}")
        path = Path(record.path)
        try:
            digest = fingerprint_plugin_binary(path)
        except (OSError, ValueError, PluginConfigError) as error:
            raise PluginUnavailableError(f"Plugin binary is unavailable: {path}") from error
        config = self.store.load()
        if matching_trust(config, path, digest) is None:
            raise PluginTrustError(f"Plugin is not allowlisted for its current bytes: {path}")
        if digest != record.binary_sha256:
            raise PluginTrustError(f"Plugin changed after the last registry scan: {path}")
        return record

    def compatibility(self, project: Project) -> list[PluginCompatibility]:
        result: list[PluginCompatibility] = []
        for track in project.tracks:
            for effect in track.effects:
                if effect.bypassed:
                    result.append(
                        PluginCompatibility(
                            instance_id=effect.id,
                            registry_id=effect.registry_id,
                            status="bypassed",
                            message="The project explicitly bypasses this effect.",
                        )
                    )
                    continue
                try:
                    record = self.require_record(effect.registry_id)
                    if record.binary_sha256 != effect.binary_sha256:
                        result.append(
                            PluginCompatibility(
                                instance_id=effect.id,
                                registry_id=effect.registry_id,
                                status="changed",
                                message="The installed plugin differs from the project snapshot.",
                            )
                        )
                    else:
                        result.append(
                            PluginCompatibility(
                                instance_id=effect.id,
                                registry_id=effect.registry_id,
                                status="ready",
                                message="The exact allowlisted plugin bytes are available.",
                            )
                        )
                except PluginTrustError as error:
                    result.append(
                        PluginCompatibility(
                            instance_id=effect.id,
                            registry_id=effect.registry_id,
                            status="untrusted",
                            message=str(error),
                        )
                    )
                except PluginUnavailableError as error:
                    result.append(
                        PluginCompatibility(
                            instance_id=effect.id,
                            registry_id=effect.registry_id,
                            status="missing",
                            message=str(error),
                        )
                    )
        return result

    def load_instance(
        self,
        effect: PluginInstance,
        *,
        sample_rate: int,
        state: bytes | None,
    ) -> list[PluginParameter]:
        record = self.require_record(effect.registry_id)
        if record.binary_sha256 != effect.binary_sha256:
            raise PluginTrustError(
                f"Installed plugin bytes do not match project instance {effect.id}"
            )
        parameters = self.worker.load(
            effect.id,
            record.path,
            effect.plugin_identifier,
            sample_rate=sample_rate,
            parameters=effect.parameters,
            state=state,
            bypassed=effect.bypassed,
        )
        self._loaded.add(effect.id)
        return parameters

    def parameters(self, instance_id: UUID) -> list[PluginParameter]:
        self._require_loaded(instance_id)
        return self.worker.parameters(instance_id)

    def set_parameter(self, instance_id: UUID, parameter_id: str, raw_value: float) -> None:
        self._require_loaded(instance_id)
        self.worker.set_parameter(instance_id, parameter_id, raw_value)

    def set_bypass(self, instance_id: UUID, bypassed: bool) -> None:
        self._require_loaded(instance_id)
        self.worker.set_bypass(instance_id, bypassed)

    def capture_state(self, instance_id: UUID, max_bytes: int) -> bytes:
        self._require_loaded(instance_id)
        state = self.worker.get_state(instance_id, max_bytes=max_bytes)
        if len(state) > max_bytes:
            raise PluginUnavailableError("Plugin state exceeds the configured limit")
        return state

    def unload(self, instance_id: UUID) -> None:
        if instance_id in self._loaded:
            self.worker.unload(instance_id)
            self._loaded.discard(instance_id)

    def close(self) -> None:
        self._loaded.clear()
        self.worker.close()

    def _require_loaded(self, instance_id: UUID) -> None:
        if instance_id not in self._loaded:
            raise PluginUnavailableError(f"Plugin instance is not loaded: {instance_id}")
