from uuid import uuid4

import numpy as np
import pytest

from vibesound.engine import AudioBuffer, InMemoryClipSourceProvider
from vibesound.engine.errors import InvalidAudioBufferError, MissingAudioSourceError


def test_audio_buffer_is_contiguous_and_read_only() -> None:
    source = np.ones((4, 1), dtype=np.float32)[::2]

    buffer = AudioBuffer(44100, source)

    assert buffer.samples.flags.c_contiguous
    assert not buffer.samples.flags.writeable
    with pytest.raises(ValueError):
        buffer.samples[0, 0] = 2.0


@pytest.mark.parametrize(
    "samples",
    [
        np.ones(4, dtype=np.float32),
        np.ones((4, 3), dtype=np.float32),
        np.array([[np.inf]], dtype=np.float32),
        np.ones((0, 1), dtype=np.float32),
    ],
)
def test_audio_buffer_rejects_invalid_shapes_or_values(samples: np.ndarray) -> None:
    with pytest.raises(InvalidAudioBufferError):
        AudioBuffer(44100, samples)


def test_in_memory_provider_reports_missing_sources() -> None:
    with pytest.raises(MissingAudioSourceError):
        InMemoryClipSourceProvider({}).get(uuid4())
