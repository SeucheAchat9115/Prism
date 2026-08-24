"""Fail-safe per-track VST3 processing for revision-pinned offline renders."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path
from uuid import UUID

import numpy as np

from prism.plugins.client import PluginWorkerClient
from prism.plugins.config import PluginConfigStore, matching_trust
from prism.plugins.errors import PluginError
from prism.plugins.registry import PluginRegistry, fingerprint_plugin_binary
from prism.plugins.types import PluginConfig
from prism.project.models import PluginInstance
from prism.project.repository import RepositorySnapshot

PluginEventPublisher = Callable[[str, dict[str, object]], None]


class IsolatedPluginRenderProcessor:
    """Load snapshot effects once and return dry audio after any unsafe failure."""

    def __init__(
        self,
        snapshot: RepositorySnapshot,
        *,
        store: PluginConfigStore | None = None,
        publisher: PluginEventPublisher | None = None,
        worker: PluginWorkerClient | None = None,
    ) -> None:
        self.snapshot = snapshot
        self.store = store or PluginConfigStore()
        self.publisher = publisher or (lambda _event, _payload: None)
        self.registry = PluginRegistry(self.store.registry_path)
        if worker is None:
            try:
                config = self.store.load()
            except PluginError:
                config = PluginConfig()
            self.worker = PluginWorkerClient(
                timeout_seconds=config.process_timeout_seconds,
                discovery_timeout_seconds=config.discovery_timeout_seconds,
            )
        else:
            self.worker = worker
        self.effects = {
            track.id: track.effects[0]
            for track in snapshot.project.tracks
            if track.effects
        }
        self._failed: set[UUID] = set()
        self._first_block: set[UUID] = set(self.effects)
        self._started = False

    @property
    def active(self) -> bool:
        return bool(self.effects)

    def start(self) -> None:
        if self._started or not self.effects:
            return
        self._started = True
        for effect in self.effects.values():
            if effect.bypassed:
                continue
            try:
                self._load(effect)
            except (PluginError, OSError, KeyError, ValueError) as error:
                self._bypass_after_failure(effect, error)

    def process(
        self,
        track_id: UUID,
        samples: np.ndarray,
        sample_rate: int,
    ) -> np.ndarray:
        effect = self.effects.get(track_id)
        if effect is None or effect.bypassed or effect.id in self._failed:
            return np.asarray(samples, dtype=np.float32)
        self.start()
        if effect.id in self._failed:
            return np.asarray(samples, dtype=np.float32)
        reset = effect.id in self._first_block
        self._first_block.discard(effect.id)
        try:
            return self.worker.process(effect.id, samples, sample_rate, reset=reset)
        except (PluginError, OSError, KeyError, ValueError) as first_error:
            self.publisher(
                "plugin.worker.failed",
                {"instance_id": str(effect.id), "message": str(first_error)},
            )
            try:
                self.worker.restart()
                self._reload_healthy()
                return self.worker.process(effect.id, samples, sample_rate, reset=True)
            except (PluginError, OSError, KeyError, ValueError) as second_error:
                self._bypass_after_failure(effect, second_error)
                return np.asarray(samples, dtype=np.float32)

    def close(self) -> None:
        self.worker.close()

    def _load(self, effect: PluginInstance) -> None:
        record = self.registry.get(effect.registry_id)
        if record is None or not record.available:
            raise PluginError(
                record.error if record is not None and record.error else "Plugin is not registered"
            )
        path = Path(record.path)
        digest = fingerprint_plugin_binary(path)
        if matching_trust(self.store.load(), path, digest) is None:
            raise PluginError("Plugin is not allowlisted for its current bytes")
        if digest != record.binary_sha256 or digest != effect.binary_sha256:
            raise PluginError("Plugin bytes do not match the project snapshot")
        state = None
        if effect.state is not None:
            state = self.snapshot.plugin_state_paths[effect.id].read_bytes()
            if (
                len(state) != effect.state.size_bytes
                or hashlib.sha256(state).hexdigest() != effect.state.sha256
            ):
                raise PluginError("Plugin state does not match the project snapshot")
        self.worker.load(
            effect.id,
            record.path,
            effect.plugin_identifier,
            sample_rate=self.snapshot.project.transport.sample_rate,
            parameters=effect.parameters,
            state=state,
        )

    def _reload_healthy(self) -> None:
        for effect in self.effects.values():
            if not effect.bypassed and effect.id not in self._failed:
                self._load(effect)
                self._first_block.add(effect.id)

    def _bypass_after_failure(self, effect: PluginInstance, error: Exception) -> None:
        self._failed.add(effect.id)
        self.publisher(
            "plugin.instance.bypassed",
            {
                "instance_id": str(effect.id),
                "registry_id": str(effect.registry_id),
                "reason": str(error),
            },
        )

    def __enter__(self) -> "IsolatedPluginRenderProcessor":
        self.start()
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()
