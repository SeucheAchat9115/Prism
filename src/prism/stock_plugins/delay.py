"""Stock tempo-synced delay effect plugin."""

from typing import Mapping

import numpy as np

from prism.plugins import Parameter, PluginDefinition


def process(
    samples: np.ndarray, parameters: Mapping[str, np.ndarray], sample_rate: int, tempo: float
) -> np.ndarray:
    output = np.zeros_like(samples)
    frames_per_beat = sample_rate * 60.0 / tempo
    delays = np.maximum(
        1, np.rint(parameters["time_beats"] * frames_per_beat).astype(np.int64)
    )
    for index in range(samples.shape[0]):
        source = index - int(delays[index])
        if source >= 0:
            output[index] = samples[source] + output[source] * parameters["feedback"][index]
    mix = parameters["mix"][:, np.newaxis]
    return np.asarray(samples * (1.0 - mix) + output * mix, dtype=np.float64)


definition = PluginDefinition(
    preset="delay",
    kind="effect",
    parameters={
        "time_beats": Parameter(0.5, 0.03125, 4.0),
        "feedback": Parameter(0.25, 0.0, 0.95),
        "mix": Parameter(0.2, 0.0, 1.0),
    },
    defaults={"time_beats": 0.5, "feedback": 0.25, "mix": 0.2},
    processor=process,
)
