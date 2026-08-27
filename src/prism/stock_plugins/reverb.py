"""Stock deterministic room reverb effect plugin."""

from typing import Mapping

import numpy as np

from prism.plugins import Parameter, PluginDefinition

_DELAYS_MS = (29.7, 37.1, 41.1, 43.7)


def process(
    samples: np.ndarray, parameters: Mapping[str, np.ndarray], sample_rate: int, tempo: float
) -> np.ndarray:
    """Create a small algorithmic room using four damped feedback delays."""

    del tempo
    frames = samples.shape[0]
    if frames == 0:
        return np.asarray(samples, dtype=np.float64).copy()

    maximum_delay = max(2, int(sample_rate * max(_DELAYS_MS) * 2.0 / 1_000.0) + 2)
    buffers = np.zeros((len(_DELAYS_MS), maximum_delay), dtype=np.float64)
    filtered = np.zeros(len(_DELAYS_MS), dtype=np.float64)
    wet = np.zeros_like(samples)
    mono = np.mean(samples, axis=1)

    for index in range(frames):
        room_size = parameters["room_size"][index]
        damping = parameters["damping"][index]
        feedback = 0.35 + room_size * 0.5
        width = parameters["width"][index]
        for line, delay_ms in enumerate(_DELAYS_MS):
            delay = max(1, int(sample_rate * delay_ms * (0.6 + room_size) / 1_000.0))
            read = (index - delay) % maximum_delay
            delayed = buffers[line, read]
            filtered[line] = delayed * (1.0 - damping) + filtered[line] * damping
            buffers[line, index % maximum_delay] = mono[index] + filtered[line] * feedback
            side = -1.0 if line % 2 == 0 else 1.0
            wet[index, 0] += filtered[line] * (1.0 - side * width * 0.5)
            wet[index, 1] += filtered[line] * (1.0 + side * width * 0.5)

    wet *= 0.25
    mix = parameters["mix"][:, np.newaxis]
    return np.asarray(samples * (1.0 - mix) + wet * mix, dtype=np.float64)


definition = PluginDefinition(
    preset="reverb",
    kind="effect",
    parameters={
        "room_size": Parameter(0.55, 0.0, 1.0),
        "damping": Parameter(0.35, 0.0, 0.95),
        "width": Parameter(0.8, 0.0, 1.0),
        "mix": Parameter(0.25, 0.0, 1.0),
    },
    defaults={"room_size": 0.55, "damping": 0.35, "width": 0.8, "mix": 0.25},
    processor=process,
)
