"""The common control surface implemented by real and fake audio backends."""

from __future__ import annotations

from typing import Protocol, Self, runtime_checkable
from uuid import UUID

from vibesound.audio.types import AudioBackendSnapshot
from vibesound.engine.sources import ClipSourceProvider
from vibesound.engine.types import EngineEvent, ScheduledAction
from vibesound.project.models import Project


@runtime_checkable
class AudioBackend(Protocol):
    """Thread-safe transport and clip controls for an audio output backend."""

    def start(self) -> None:
        """Start or resume playback."""

    def pause(self) -> None:
        """Pause playback while preserving the engine position."""

    def stop(self) -> None:
        """Stop playback and release the output device when applicable."""

    def reset(self) -> None:
        """Stop playback and return the engine timeline to frame zero."""

    def launch_slot(self, track_id: UUID, scene_id: UUID) -> ScheduledAction:
        """Launch a track/scene slot using the engine's quantization rules."""

    def launch_scene(self, scene_id: UUID) -> ScheduledAction:
        """Launch all populated slots in a scene."""

    def stop_track(self, track_id: UUID) -> ScheduledAction:
        """Stop one track using the engine's quantization rules."""

    def stop_all(self) -> ScheduledAction:
        """Stop every active track at one engine boundary."""

    def snapshot(self) -> AudioBackendSnapshot:
        """Return backend state and diagnostics without exposing mutable state."""

    def update_mixer(self, project: Project) -> None:
        """Apply runtime-safe mixer values without rebuilding the backend."""

    def replace_project(self, project: Project, sources: ClipSourceProvider) -> None:
        """Replace the engine graph while preserving compatible runtime state."""

    def drain_events(self) -> tuple[EngineEvent, ...]:
        """Return actual engine transitions produced since the previous call."""

    def close(self) -> None:
        """Release all backend resources."""

    def __enter__(self) -> Self:
        """Return the backend as a context manager."""

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        """Release resources at context-manager exit."""
