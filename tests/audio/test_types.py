from __future__ import annotations

import pytest

from prism.audio import AudioBackendConfig, AudioBackendState, AudioDeviceInfo


def test_audio_config_has_balanced_defaults() -> None:
    config = AudioBackendConfig()

    assert config.block_size == 512
    assert config.queue_blocks == 4
    assert config.device is None


def test_audio_config_rejects_invalid_values() -> None:
    with pytest.raises(ValueError):
        AudioBackendConfig(block_size=0)
    with pytest.raises(ValueError):
        AudioBackendConfig(queue_blocks=1)
    with pytest.raises(ValueError):
        AudioBackendConfig(sample_rate=0)


def test_audio_device_info_and_state_are_typed_values() -> None:
    device = AudioDeviceInfo(2, "Speakers", "WASAPI", 2, 48000.0)

    assert device.index == 2
    assert device.max_output_channels == 2
    assert AudioBackendState.RUNNING.value == "running"
