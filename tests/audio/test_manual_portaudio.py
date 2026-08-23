from __future__ import annotations

import time

import numpy as np
import pytest

from prism.audio import AudioBackendConfig, AudioBackendState, PortAudioBackend

from ._helpers import make_audio_fixture


@pytest.mark.audio_device
def test_fixture_plays_on_the_default_windows_output_device() -> None:
    sample_rate = 44100
    frames = sample_rate * 3
    values = np.sin(np.arange(frames, dtype=np.float32) * (2.0 * np.pi * 440.0 / sample_rate))
    project, provider, track, scene, _ = make_audio_fixture(
        frames=frames,
        sample_rate=sample_rate,
        samples=values,
    )
    backend = PortAudioBackend(
        project,
        provider,
        config=AudioBackendConfig(block_size=512, queue_blocks=4),
    )
    backend.launch_slot(track.id, scene.id)
    backend.start()
    time.sleep(2.0)
    snapshot = backend.snapshot()
    backend.stop()
    backend.close()

    assert snapshot.state == AudioBackendState.RUNNING
    assert snapshot.last_error is None
