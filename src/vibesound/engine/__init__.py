"""Deterministic, in-memory session engine primitives."""

from vibesound.engine.clock import TransportClock
from vibesound.engine.errors import (
    EngineError,
    EngineValidationError,
    InvalidAudioBufferError,
    InvalidEngineCommandError,
    MissingAudioSourceError,
)
from vibesound.engine.session import SessionEngine
from vibesound.engine.sinks import AudioSink, FakeAudioSink
from vibesound.engine.sources import AudioBuffer, ClipSourceProvider, InMemoryClipSourceProvider
from vibesound.engine.types import (
    ClipCompletedEvent,
    ClipLaunchedEvent,
    ClipStoppedEvent,
    EngineEvent,
    EngineSnapshot,
    EngineStep,
    ScheduledAction,
    TransportChangedEvent,
    TransportMode,
)

__all__ = [
    "AudioBuffer",
    "AudioSink",
    "ClipLaunchedEvent",
    "ClipCompletedEvent",
    "ClipSourceProvider",
    "ClipStoppedEvent",
    "EngineError",
    "EngineEvent",
    "EngineSnapshot",
    "EngineStep",
    "EngineValidationError",
    "FakeAudioSink",
    "InMemoryClipSourceProvider",
    "InvalidAudioBufferError",
    "InvalidEngineCommandError",
    "MissingAudioSourceError",
    "ScheduledAction",
    "SessionEngine",
    "TransportChangedEvent",
    "TransportClock",
    "TransportMode",
]
