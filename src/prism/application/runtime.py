"""Audio runtime ownership, device fallback, graph refresh, and actual events."""

from __future__ import annotations

from collections.abc import Callable
from threading import Event, RLock, Thread
from typing import TypeAlias
from uuid import UUID

from prism.application.types import RuntimeImpact
from prism.audio import (
    AudioBackend,
    AudioBackendConfig,
    AudioBackendError,
    AudioBackendSnapshot,
    AudioDeviceError,
    AudioDeviceInfo,
    FakeAudioBackend,
    PortAudioBackend,
    list_output_devices,
)
from prism.engine import ClipCompletedEvent, EngineEvent
from prism.engine.sources import ClipSourceProvider
from prism.engine.types import ScheduledAction
from prism.project import ProjectRepository
from prism.project.models import Project
from prism.rendering import prepare_working_playback_project

BackendFactory: TypeAlias = Callable[[Project, ClipSourceProvider], AudioBackend]
RuntimePublisher = Callable[[str, dict[str, object]], None]


class AudioRuntimeCoordinator:
    """Keep device and engine concerns outside metadata command processing."""

    def __init__(
        self,
        repository: ProjectRepository,
        *,
        backend_factory: BackendFactory | None = None,
        publisher: RuntimePublisher | None = None,
    ) -> None:
        self._repository = repository
        self._factory = backend_factory
        self._publisher = publisher or (lambda _event, _payload: None)
        self._lock = RLock()
        self._closed = False
        self._monitor_stop = Event()
        prepared = prepare_working_playback_project(repository.snapshot())
        self._runtime_project = prepared.project
        self._runtime_sources = prepared.sources
        self._backend = self._make_backend(prepared.project, prepared.sources)
        self._monitor = Thread(
            target=self._monitor_events,
            name="prism-runtime-events",
            daemon=True,
        )
        self._monitor.start()

    def snapshot(self) -> AudioBackendSnapshot:
        with self._lock:
            self._require_open()
            return self._backend.snapshot()

    def transport(self, operation: str) -> AudioBackendSnapshot:
        with self._lock:
            self._require_open()
            backend_operation = "start" if operation == "play" else operation
            try:
                getattr(self._backend, backend_operation)()
            except AudioBackendError:
                if operation != "play" or isinstance(self._backend, FakeAudioBackend):
                    raise
                failed = self._backend
                self._backend = FakeAudioBackend(
                    self._runtime_project,
                    self._runtime_sources,
                )
                failed.close()
                self._backend.start()
                self._publisher(
                    "audio.device_fallback",
                    {
                        "reason": "No usable output device; continuing device-free.",
                    },
                )
            return self._backend.snapshot()

    def launch_slot(self, track_id: UUID, scene_id: UUID) -> ScheduledAction:
        with self._lock:
            self._require_open()
            return self._backend.launch_slot(track_id, scene_id)

    def stop_track(self, track_id: UUID) -> ScheduledAction:
        with self._lock:
            self._require_open()
            return self._backend.stop_track(track_id)

    def apply_project(self, project: Project, impact: RuntimeImpact) -> bool:
        """Apply a committed project and return whether a reset was performed."""

        with self._lock:
            self._require_open()
            if impact == RuntimeImpact.NONE:
                return False
            if impact == RuntimeImpact.INCREMENTAL:
                self._backend.update_mixer(project)
                self._runtime_project = project.model_copy(deep=True)
                return False
            prepared = prepare_working_playback_project(self._repository.snapshot())
            if impact == RuntimeImpact.RESET:
                self._backend.reset()
            self._backend.replace_project(prepared.project, prepared.sources)
            self._runtime_project = prepared.project
            self._runtime_sources = prepared.sources
            return impact == RuntimeImpact.RESET

    def devices(self) -> tuple[AudioDeviceInfo, ...]:
        try:
            return list_output_devices()
        except AudioBackendError:
            return ()

    def restart(self, device: int | str | None = None) -> AudioBackendSnapshot:
        """Recreate output explicitly; fall back to device-free mode on failure."""

        with self._lock:
            self._require_open()
            previous = self._backend
            devices = self.devices()
            if device is not None:
                matches = [
                    item
                    for item in devices
                    if item.index == device or item.name == device
                ]
                if len(matches) != 1:
                    raise AudioDeviceError(
                        f"Output device is unavailable or ambiguous: {device!r}"
                    )
            if not devices:
                replacement: AudioBackend = FakeAudioBackend(
                    self._runtime_project,
                    self._runtime_sources,
                )
            else:
                replacement = PortAudioBackend(
                    self._runtime_project,
                    self._runtime_sources,
                    config=AudioBackendConfig(device=device),
                )
            self._backend = replacement
            previous.close()
            self._publisher(
                "audio.restarted",
                {
                    "device": device,
                    "device_free": isinstance(replacement, FakeAudioBackend),
                    "runtime_reset_performed": True,
                },
            )
            return replacement.snapshot()

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._monitor_stop.set()
            backend = self._backend
        self._monitor.join(timeout=2.0)
        backend.close()

    def _make_backend(self, project: Project, sources: ClipSourceProvider) -> AudioBackend:
        if self._factory is not None:
            backend = self._factory(project, sources)
            if not isinstance(backend, AudioBackend):
                raise TypeError("Audio backend factory returned an incompatible backend")
            return backend
        try:
            if not list_output_devices():
                return FakeAudioBackend(project, sources)
            return PortAudioBackend(project, sources)
        except AudioBackendError:
            return FakeAudioBackend(project, sources)

    def _monitor_events(self) -> None:
        while not self._monitor_stop.wait(0.02):
            try:
                with self._lock:
                    if self._closed:
                        return
                    events = self._backend.drain_events()
            except AudioBackendError:
                continue
            for event in events:
                self._publish_engine_event(event)

    def _publish_engine_event(self, event: EngineEvent) -> None:
        if event.kind == "transport.changed":
            return
        payload: dict[str, object] = {"frame": event.frame}
        for name in ("track_id", "scene_id", "clip_id", "position_frame", "mode"):
            if not hasattr(event, name):
                continue
            value = getattr(event, name)
            payload[name] = value.value if hasattr(value, "value") else str(value)
        event_type = "clip.completed" if isinstance(event, ClipCompletedEvent) else event.kind
        self._publisher(event_type, payload)

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeError("Audio runtime coordinator is closed")
