"""Real-time, fake, and offline audio backend interfaces."""

from vibesound.audio.base import AudioBackend
from vibesound.audio.errors import (
    AudioBackendError,
    AudioCallbackError,
    AudioCommandTimeoutError,
    AudioConfigurationError,
    AudioDeviceError,
    AudioRuntimeError,
    AudioStateError,
)
from vibesound.audio.fake import FakeAudioBackend
from vibesound.audio.offline import OfflineRenderBackend
from vibesound.audio.portaudio import PortAudioBackend, list_output_devices
from vibesound.audio.types import (
    AudioBackendConfig,
    AudioBackendSnapshot,
    AudioBackendState,
    AudioDeviceInfo,
    AudioErrorInfo,
)

__all__ = [
    "AudioBackend",
    "AudioBackendConfig",
    "AudioBackendError",
    "AudioBackendSnapshot",
    "AudioBackendState",
    "AudioCallbackError",
    "AudioCommandTimeoutError",
    "AudioConfigurationError",
    "AudioDeviceError",
    "AudioDeviceInfo",
    "AudioErrorInfo",
    "AudioRuntimeError",
    "AudioStateError",
    "FakeAudioBackend",
    "OfflineRenderBackend",
    "PortAudioBackend",
    "list_output_devices",
]
