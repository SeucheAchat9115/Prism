"""Real-time, fake, and offline audio backend interfaces."""

from prism.audio.base import AudioBackend
from prism.audio.errors import (
    AudioBackendError,
    AudioCallbackError,
    AudioCommandTimeoutError,
    AudioConfigurationError,
    AudioDeviceError,
    AudioRuntimeError,
    AudioStateError,
)
from prism.audio.fake import FakeAudioBackend
from prism.audio.offline import OfflineRenderBackend
from prism.audio.portaudio import PortAudioBackend, list_output_devices
from prism.audio.types import (
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
