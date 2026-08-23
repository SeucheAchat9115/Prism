"""Device-free backend implementation for tests and deterministic callers."""

from __future__ import annotations

from threading import RLock
from uuid import UUID

from vibesound.audio.base import AudioBackend
from vibesound.audio.errors import AudioConfigurationError, AudioStateError
from vibesound.audio.types import (
    AudioBackendConfig,
    AudioBackendSnapshot,
    AudioBackendState,
)
from vibesound.engine import EngineEvent, EngineStep, SessionEngine
from vibesound.engine.sources import ClipSourceProvider
from vibesound.engine.types import ScheduledAction
from vibesound.project.models import Project


class FakeAudioBackend:
    """Run the backend control surface without opening a hardware device."""

    def __init__(
        self,
        project: Project,
        sources: ClipSourceProvider,
        *,
        config: AudioBackendConfig | None = None,
    ) -> None:
        self._config = config or AudioBackendConfig()
        if (
            self._config.sample_rate is not None
            and self._config.sample_rate != project.transport.sample_rate
        ):
            raise AudioConfigurationError(
                "Audio backend sample_rate must match the project's transport sample_rate"
            )
        self._engine = SessionEngine(project, sources)
        self._lock = RLock()
        self._state = AudioBackendState.STOPPED
        self._snapshot = self._engine.snapshot()
        self._events: list[EngineEvent] = []
        self._closed = False

    def start(self) -> None:
        with self._lock:
            self._require_open()
            self._engine.play()
            self._state = AudioBackendState.RUNNING
            self._capture_events()
            self._refresh()

    def pause(self) -> None:
        with self._lock:
            self._require_open()
            self._engine.pause()
            self._state = AudioBackendState.PAUSED
            self._capture_events()
            self._refresh()

    def stop(self) -> None:
        with self._lock:
            self._require_open()
            self._engine.stop()
            self._state = AudioBackendState.STOPPED
            self._capture_events()
            self._refresh()

    def reset(self) -> None:
        with self._lock:
            self._require_open()
            self._engine.reset()
            self._state = AudioBackendState.STOPPED
            self._capture_events()
            self._refresh()

    def launch_slot(self, track_id: UUID, scene_id: UUID) -> ScheduledAction:
        with self._lock:
            self._require_open()
            action = self._engine.launch_slot(track_id, scene_id)
            self._capture_events()
            self._refresh()
            return action

    def launch_scene(self, scene_id: UUID) -> ScheduledAction:
        with self._lock:
            self._require_open()
            action = self._engine.launch_scene(scene_id)
            self._capture_events()
            self._refresh()
            return action

    def stop_track(self, track_id: UUID) -> ScheduledAction:
        with self._lock:
            self._require_open()
            action = self._engine.stop_track(track_id)
            self._capture_events()
            self._refresh()
            return action

    def stop_all(self) -> ScheduledAction:
        with self._lock:
            self._require_open()
            action = self._engine.stop_all()
            self._capture_events()
            self._refresh()
            return action

    def advance(self, frames: int) -> EngineStep:
        """Advance fake playback deterministically and return the engine step."""

        with self._lock:
            self._require_open()
            step = self._engine.advance(frames)
            self._events.extend(step.events)
            self._refresh()
            return step

    def update_mixer(self, project: Project) -> None:
        with self._lock:
            self._require_open()
            self._engine.update_mixer(project)
            self._refresh()

    def replace_project(self, project: Project, sources: ClipSourceProvider) -> None:
        with self._lock:
            self._require_open()
            self._engine = self._engine.reconfigured(project, sources)
            self._capture_events()
            self._refresh()

    def drain_events(self) -> tuple[EngineEvent, ...]:
        with self._lock:
            self._require_open()
            self._capture_events()
            events = tuple(self._events)
            self._events.clear()
            return events

    def snapshot(self) -> AudioBackendSnapshot:
        with self._lock:
            return AudioBackendSnapshot(
                state=self._state,
                engine_snapshot=self._snapshot,
                device=None,
                underrun_count=0,
                last_error=None,
            )

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._state = AudioBackendState.CLOSED

    def __enter__(self) -> "FakeAudioBackend":
        self._require_open()
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.close()

    def _require_open(self) -> None:
        if self._closed:
            raise AudioStateError("Audio backend is closed")

    def _refresh(self) -> None:
        self._snapshot = self._engine.snapshot()

    def _capture_events(self) -> None:
        self._events.extend(self._engine.drain_events())


def is_audio_backend(value: object) -> bool:
    """Return whether a value satisfies the public backend protocol."""

    return isinstance(value, AudioBackend)
