"""Deterministic, in-memory session engine primitives."""

from prism.engine.clock import TransportClock
from prism.engine.errors import (
    EngineError,
    EngineValidationError,
    InvalidAudioBufferError,
    InvalidEngineCommandError,
    MissingAudioSourceError,
)
from prism.engine.session import SessionEngine, TrackEffectProcessor
from prism.engine.sinks import AudioSink, FakeAudioSink
from prism.engine.sources import AudioBuffer, ClipSourceProvider, InMemoryClipSourceProvider
from prism.engine.types import (
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
    "TrackEffectProcessor",
    "TransportChangedEvent",
    "TransportClock",
    "TransportMode",
]
