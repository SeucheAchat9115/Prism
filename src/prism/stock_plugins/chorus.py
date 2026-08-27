"""Stock stereo chorus effect plugin."""

from typing import Mapping

import numpy as np

from prism.plugins import Parameter, PluginDefinition


def process(
    samples: np.ndarray, parameters: Mapping[str, np.ndarray], sample_rate: int, tempo: float
) -> np.ndarray:
    """Add a short, slowly modulated stereo delay."""

    del tempo
    frames = samples.shape[0]
    if frames == 0:
        return np.asarray(samples, dtype=np.float64).copy()

    phase = np.cumsum(2.0 * np.pi * parameters["rate_hz"] / sample_rate)
    depth_frames = parameters["depth_ms"] * sample_rate / 1_000.0
    base_frames = 8.0 * sample_rate / 1_000.0
    wet = np.zeros_like(samples)
    positions = np.arange(frames, dtype=np.float64)

    for channel, offset in enumerate((0.0, np.pi / 2.0)):
        delay = base_frames + depth_frames * (0.5 + 0.5 * np.sin(phase + offset))
        source = positions - delay
        valid = source >= 0.0
        left = np.floor(np.maximum(source, 0.0)).astype(np.int64)
        right = np.minimum(left + 1, frames - 1)
        fraction = source - left
        interpolated = (
            samples[left, channel] * (1.0 - fraction)
            + samples[right, channel] * fraction
        )
        wet[valid, channel] = interpolated[valid]

    mix = parameters["mix"][:, np.newaxis]
    return np.asarray(samples * (1.0 - mix) + wet * mix, dtype=np.float64)


definition = PluginDefinition(
    preset="chorus",
    kind="effect",
    parameters={
        "rate_hz": Parameter(0.8, 0.05, 10.0),
        "depth_ms": Parameter(6.0, 0.0, 20.0),
        "mix": Parameter(0.3, 0.0, 1.0),
    },
    defaults={"rate_hz": 0.8, "depth_ms": 6.0, "mix": 0.3},
    processor=process,
)
