"""A preallocated single-producer/single-consumer audio block ring."""

from __future__ import annotations

import numpy as np


class AudioRingBuffer:
    """Store fixed stereo float32 blocks without callback-side allocation or locks."""

    channels = 2

    def __init__(self, block_size: int, capacity: int) -> None:
        if not isinstance(block_size, int) or isinstance(block_size, bool) or block_size <= 0:
            raise ValueError("block_size must be a positive integer")
        if not isinstance(capacity, int) or isinstance(capacity, bool) or capacity < 2:
            raise ValueError("capacity must be at least 2 blocks")
        self.block_size = block_size
        self.capacity = capacity
        self._storage = np.zeros((capacity, block_size, self.channels), dtype=np.float32)
        self._generations = np.zeros(capacity, dtype=np.int64)
        self._write_sequence = 0
        self._read_sequence = 0
        self._released_sequence = 0
        self._current_sequence: int | None = None
        self._current_offset = 0
        self._generation = 0
        self._minimum_generation = 0

    @property
    def generation(self) -> int:
        """Return the generation assigned to subsequently written blocks."""

        return self._generation

    @property
    def queued_blocks(self) -> int:
        """Return blocks not yet fully released by the consumer."""

        return self._write_sequence - self._released_sequence

    def invalidate(self) -> int:
        """Mark all currently queued blocks stale and return the new generation."""

        self._generation += 1
        self._minimum_generation = self._generation
        return self._generation

    def try_write(self, samples: np.ndarray) -> bool:
        """Write one full block from the producer, returning false when full."""

        if samples.dtype != np.dtype(np.float32) or samples.shape != (
            self.block_size,
            self.channels,
        ):
            raise ValueError("Audio ring writes require an exact stereo float32 block")
        if self._write_sequence - self._released_sequence >= self.capacity:
            return False
        index = self._write_sequence % self.capacity
        np.copyto(self._storage[index], samples, casting="no")
        self._generations[index] = self._generation
        self._write_sequence += 1
        return True

    def read_into(self, output: np.ndarray, *, muted: bool = False) -> bool:
        """Fill callback output and return whether a non-muted underrun occurred."""

        if output.ndim != 2 or output.shape[1] != self.channels:
            raise ValueError("Audio ring reads require a stereo output array")
        output.fill(0.0)
        if muted:
            self._discard_available()
            return False

        frames = output.shape[0]
        cursor = 0
        underrun = False
        while cursor < frames:
            if self._current_sequence is None:
                if self._read_sequence >= self._write_sequence:
                    underrun = True
                    break
                self._current_sequence = self._read_sequence
                self._read_sequence += 1
                self._current_offset = 0

            sequence = self._current_sequence
            index = sequence % self.capacity
            if self._generations[index] < self._minimum_generation:
                self._release_current()
                continue

            count = min(frames - cursor, self.block_size - self._current_offset)
            np.copyto(
                output[cursor : cursor + count],
                self._storage[index][self._current_offset : self._current_offset + count],
                casting="no",
            )
            cursor += count
            self._current_offset += count
            if self._current_offset == self.block_size:
                self._release_current()
        return underrun

    def _release_current(self) -> None:
        if self._current_sequence is None:
            return
        self._released_sequence = self._current_sequence + 1
        self._current_sequence = None
        self._current_offset = 0

    def _discard_available(self) -> None:
        self._release_current()
        while self._read_sequence < self._write_sequence:
            self._read_sequence += 1
            self._released_sequence = self._read_sequence
