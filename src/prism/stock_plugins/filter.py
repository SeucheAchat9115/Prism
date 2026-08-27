"""Stock one-pole filter effect plugin."""

from typing import Mapping

import numpy as np

from prism.plugins import Parameter, PluginDefinition


def process(
    samples: np.ndarray, parameters: Mapping[str, np.ndarray], sample_rate: int, tempo: float
) -> np.ndarray:
    del tempo
    output = low_pass(samples, parameters["cutoff_hz"], sample_rate)
    mix = parameters["mix"][:, np.newaxis]
    return np.asarray(samples * (1.0 - mix) + output * mix, dtype=np.float64)


def low_pass(samples: np.ndarray, cutoff: np.ndarray, sample_rate: int) -> np.ndarray:
    cutoff = np.clip(cutoff, 20.0, sample_rate * 0.45)
    alpha = 1.0 - np.exp(-2.0 * np.pi * cutoff / sample_rate)
    output = np.empty_like(samples)
    state = np.zeros(2, dtype=np.float64)
    for index in range(samples.shape[0]):
        state += alpha[index] * (samples[index] - state)
        output[index] = state
    return np.asarray(output, dtype=np.float64)


definition = PluginDefinition(
    preset="filter",
    kind="effect",
    parameters={
        "cutoff_hz": Parameter(1_200.0, 20.0, 20_000.0),
        "mix": Parameter(1.0, 0.0, 1.0),
    },
    defaults={"cutoff_hz": 1_200.0, "mix": 1.0},
    processor=process,
)
