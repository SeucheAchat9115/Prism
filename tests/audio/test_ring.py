from __future__ import annotations

import numpy as np

from prism.audio.ring import AudioRingBuffer


def test_ring_reads_blocks_and_reports_empty_underruns() -> None:
    ring = AudioRingBuffer(block_size=2, capacity=2)
    first = np.asarray([[1.0, 1.0], [2.0, 2.0]], dtype=np.float32)
    second = np.asarray([[3.0, 3.0], [4.0, 4.0]], dtype=np.float32)
    output = np.empty((2, 2), dtype=np.float32)

    assert ring.try_write(first)
    assert ring.try_write(second)
    assert not ring.try_write(first)
    assert not ring.read_into(output)
    np.testing.assert_array_equal(output, first)
    assert not ring.read_into(output)
    np.testing.assert_array_equal(output, second)
    assert ring.read_into(output)
    np.testing.assert_array_equal(output, np.zeros((2, 2), dtype=np.float32))


def test_ring_supports_partial_reads_and_generation_invalidation() -> None:
    ring = AudioRingBuffer(block_size=4, capacity=2)
    block = np.arange(8, dtype=np.float32).reshape(4, 2)
    first = np.empty((2, 2), dtype=np.float32)
    second = np.empty((2, 2), dtype=np.float32)
    stale = np.empty((2, 2), dtype=np.float32)

    assert ring.try_write(block)
    assert not ring.read_into(first)
    assert not ring.read_into(second)
    np.testing.assert_array_equal(first, block[:2])
    np.testing.assert_array_equal(second, block[2:])

    assert ring.try_write(block)
    ring.invalidate()
    assert ring.read_into(stale)
    np.testing.assert_array_equal(stale, np.zeros((2, 2), dtype=np.float32))


def test_muted_ring_output_is_silent_and_drains_queued_blocks() -> None:
    ring = AudioRingBuffer(block_size=2, capacity=2)
    block = np.ones((2, 2), dtype=np.float32)
    output = np.empty((2, 2), dtype=np.float32)
    assert ring.try_write(block)

    assert not ring.read_into(output, muted=True)
    np.testing.assert_array_equal(output, np.zeros((2, 2), dtype=np.float32))
    assert ring.queued_blocks == 0
