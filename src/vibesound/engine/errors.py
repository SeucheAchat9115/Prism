"""Errors raised by the deterministic session engine."""


class EngineError(Exception):
    """Base class for session engine failures."""


class EngineValidationError(EngineError):
    """The project, source buffers, or engine configuration is invalid."""


class InvalidAudioBufferError(EngineValidationError):
    """An injected audio buffer does not satisfy the engine contract."""


class MissingAudioSourceError(EngineValidationError):
    """A referenced project asset has no injected audio source."""


class InvalidEngineCommandError(EngineError):
    """A session command cannot be applied to the current engine."""
