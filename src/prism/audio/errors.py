"""Typed failures for Prism audio backends."""


class AudioBackendError(Exception):
    """Base class for audio backend failures."""


class AudioConfigurationError(AudioBackendError):
    """The backend configuration or project cannot be used for playback."""


class AudioStateError(AudioBackendError):
    """An operation is invalid for the backend's current lifecycle state."""


class AudioDeviceError(AudioBackendError):
    """An output device could not be discovered, opened, or released."""


class AudioCallbackError(AudioBackendError):
    """The PortAudio callback encountered a runtime failure or underrun."""


class AudioCommandTimeoutError(AudioBackendError):
    """A worker-owned backend command did not complete before its deadline."""


class AudioRuntimeError(AudioBackendError):
    """A backend worker failed outside the PortAudio callback."""
