"""Stock distortion effect plugin."""

from typing import Mapping

import numpy as np

from prism.plugins import Parameter, PluginDefinition


def process(
    samples: np.ndarray, parameters: Mapping[str, np.ndarray], sample_rate: int, tempo: float
) -> np.ndarray:
    del sample_rate, tempo
    drive = np.power(10.0, parameters["drive_db"] / 20.0)
    wet = np.tanh(samples * drive[:, np.newaxis]) / np.tanh(
        np.maximum(drive[:, np.newaxis], 1.0)
    )
    mix = parameters["mix"][:, np.newaxis]
    return np.asarray(samples * (1.0 - mix) + wet * mix, dtype=np.float64)


definition = PluginDefinition(
    preset="distortion",
    kind="effect",
    parameters={
        "drive_db": Parameter(12.0, 0.0, 36.0),
        "mix": Parameter(0.5, 0.0, 1.0),
    },
    defaults={"drive_db": 12.0, "mix": 0.5},
    processor=process,
)
