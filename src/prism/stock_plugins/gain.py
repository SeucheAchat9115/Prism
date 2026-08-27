"""Stock gain effect plugin."""

from typing import Mapping

import numpy as np

from prism.plugins import Parameter, PluginDefinition


def process(
    samples: np.ndarray, parameters: Mapping[str, np.ndarray], sample_rate: int, tempo: float
) -> np.ndarray:
    del sample_rate, tempo
    return np.asarray(samples * db_envelope(parameters["gain_db"])[:, np.newaxis], dtype=np.float64)


def db_envelope(values: np.ndarray) -> np.ndarray:
    return np.asarray(np.power(10.0, values / 20.0), dtype=np.float64)


definition = PluginDefinition(
    preset="gain",
    kind="effect",
    parameters={"gain_db": Parameter(0.0, -60.0, 12.0)},
    defaults={"gain_db": 0.0},
    processor=process,
)
