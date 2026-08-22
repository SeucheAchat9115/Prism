import numpy as np

from vibesound.engine import FakeAudioSink


def test_fake_sink_collects_stereo_blocks() -> None:
    sink = FakeAudioSink()
    sink.write(np.ones((2, 2), dtype=np.float32))
    sink.write(np.full((1, 2), 2.0, dtype=np.float32))

    assert sink.frames_written == 3
    np.testing.assert_array_equal(
        sink.render(),
        np.asarray([[1.0, 1.0], [1.0, 1.0], [2.0, 2.0]], dtype=np.float32),
    )
