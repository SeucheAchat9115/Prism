from __future__ import annotations

import time

import numpy as np
import pytest

from prism.audio import (
    AudioBackendConfig,
    AudioBackendState,
    AudioDeviceInfo,
    PortAudioBackend,
    list_output_devices,
    portaudio,
)
from prism.audio.errors import AudioDeviceError

from ._helpers import FakeOutputStream, make_audio_fixture


class _Status:
    output_underflow = True


def _install_fake_devices(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        portaudio.sd,
        "query_devices",
        lambda *args: [
            {
                "name": "Stereo Speakers",
                "max_output_channels": 2,
                "default_samplerate": 8.0,
                "hostapi": 0,
            },
            {
                "name": "Mono Monitor",
                "max_output_channels": 1,
                "default_samplerate": 8.0,
                "hostapi": 0,
            },
        ],
    )
    monkeypatch.setattr(portaudio.sd, "query_hostapis", lambda: [{"name": "FakeHost"}])
    monkeypatch.setattr(portaudio.sd.default, "device", [0, 0])


def test_list_output_devices_filters_to_stereo_outputs(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_devices(monkeypatch)

    devices = list_output_devices()

    assert devices == (AudioDeviceInfo(0, "Stereo Speakers", "FakeHost", 2, 8.0),)


def test_portaudio_backend_configures_stream_and_forwards_audio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_devices(monkeypatch)
    FakeOutputStream.instances.clear()
    monkeypatch.setattr(portaudio.sd, "OutputStream", FakeOutputStream)
    project, provider, track, scene, _ = make_audio_fixture(frames=64)
    backend = PortAudioBackend(
        project,
        provider,
        config=AudioBackendConfig(block_size=2, queue_blocks=4),
    )
    backend.launch_slot(track.id, scene.id)

    backend.start()
    stream = FakeOutputStream.instances[-1]
    output = stream.pull(2)

    assert stream.kwargs["samplerate"] == project.transport.sample_rate
    assert stream.kwargs["blocksize"] == 2
    assert stream.kwargs["channels"] == 2
    assert stream.kwargs["dtype"] == "float32"
    assert stream.started
    np.testing.assert_allclose(output, np.full((2, 2), 1.0 / np.sqrt(2.0)))
    assert backend.snapshot().state == AudioBackendState.RUNNING

    backend.pause()
    np.testing.assert_array_equal(stream.pull(2), np.zeros((2, 2), dtype=np.float32))
    backend.stop()
    assert stream.stopped
    assert stream.closed
    assert backend.snapshot().state == AudioBackendState.STOPPED
    backend.close()


def test_portaudio_backend_recovers_isolated_underflow_then_faults_at_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_devices(monkeypatch)
    monkeypatch.setattr(portaudio.sd, "OutputStream", FakeOutputStream)
    project, provider, _, _, _ = make_audio_fixture(frames=64)
    backend = PortAudioBackend(project, provider, config=AudioBackendConfig(block_size=2))
    backend.start()
    stream = FakeOutputStream.instances[-1]
    stream.pull(2, _Status())

    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline and backend.snapshot().last_error is None:
        time.sleep(0.01)
    snapshot = backend.snapshot()

    assert snapshot.state == AudioBackendState.RUNNING
    assert snapshot.last_error is not None
    assert snapshot.last_error.code == "output_underflow"
    assert snapshot.last_error.recoverable
    assert snapshot.underrun_count >= 1

    for _ in range(7):
        stream.pull(2, _Status())
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline and backend.snapshot().state != AudioBackendState.FAULTED:
        time.sleep(0.01)
    snapshot = backend.snapshot()

    assert snapshot.state == AudioBackendState.FAULTED
    assert snapshot.last_error is not None
    assert not snapshot.last_error.recoverable
    backend.close()


def test_portaudio_backend_surfaces_stream_open_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_devices(monkeypatch)

    class FailingStream:
        def __init__(self, **kwargs: object) -> None:
            del kwargs
            raise RuntimeError("device unavailable")

    monkeypatch.setattr(portaudio.sd, "OutputStream", FailingStream)
    project, provider, _, _, _ = make_audio_fixture()
    backend = PortAudioBackend(project, provider)

    with pytest.raises(AudioDeviceError):
        backend.start()
    assert backend.snapshot().state == AudioBackendState.FAULTED
    backend.close()
