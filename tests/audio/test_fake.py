from __future__ import annotations

import numpy as np
import pytest

from prism.audio import AudioBackendState, FakeAudioBackend
from prism.audio.errors import AudioStateError

from ._helpers import make_audio_fixture


def test_fake_backend_matches_engine_controls_without_a_device() -> None:
    project, provider, track, scene, _ = make_audio_fixture()
    backend = FakeAudioBackend(project, provider)

    assert backend.snapshot().state == AudioBackendState.STOPPED
    action = backend.launch_slot(track.id, scene.id)
    assert action.changed

    backend.start()
    step = backend.advance(2)
    assert backend.snapshot().state == AudioBackendState.RUNNING
    assert step.end_frame == 2
    np.testing.assert_allclose(step.samples, np.full((2, 2), 1.0 / np.sqrt(2.0)))

    backend.pause()
    paused = backend.advance(2)
    assert backend.snapshot().state == AudioBackendState.PAUSED
    assert paused.start_frame == paused.end_frame == 2
    np.testing.assert_array_equal(paused.samples, np.zeros((2, 2), dtype=np.float32))

    backend.stop()
    assert backend.snapshot().state == AudioBackendState.STOPPED
    backend.reset()
    assert backend.snapshot().engine_snapshot.position_frame == 0

    backend.close()
    backend.close()
    with pytest.raises(AudioStateError):
        backend.start()
