"""Stock dynamics compressor effect plugin."""

from typing import Mapping

import numpy as np

from prism.plugins import Parameter, PluginDefinition


def process(
    samples: np.ndarray, parameters: Mapping[str, np.ndarray], sample_rate: int, tempo: float
) -> np.ndarray:
    """Apply linked-stereo compression with smoothed gain reduction."""

    del tempo
    wet = np.empty_like(samples)
    reduction_db = 0.0
    for index in range(samples.shape[0]):
        peak = max(float(np.max(np.abs(samples[index]))), 1e-12)
        level_db = 20.0 * np.log10(peak)
        ratio = parameters["ratio"][index]
        over_db = max(0.0, level_db - parameters["threshold_db"][index])
        target_db = over_db * (1.0 - 1.0 / ratio)
        time_ms = (
            parameters["attack_ms"][index]
            if target_db > reduction_db
            else parameters["release_ms"][index]
        )
        coefficient = np.exp(-1.0 / (sample_rate * time_ms / 1_000.0))
        reduction_db = coefficient * reduction_db + (1.0 - coefficient) * target_db
        gain_db = parameters["makeup_db"][index] - reduction_db
        wet[index] = samples[index] * np.power(10.0, gain_db / 20.0)

    mix = parameters["mix"][:, np.newaxis]
    return np.asarray(samples * (1.0 - mix) + wet * mix, dtype=np.float64)


definition = PluginDefinition(
    preset="compressor",
    kind="effect",
    parameters={
        "threshold_db": Parameter(-18.0, -60.0, 0.0),
        "ratio": Parameter(4.0, 1.0, 20.0),
        "attack_ms": Parameter(10.0, 0.1, 200.0),
        "release_ms": Parameter(100.0, 5.0, 2_000.0),
        "makeup_db": Parameter(0.0, 0.0, 24.0),
        "mix": Parameter(1.0, 0.0, 1.0),
    },
    defaults={
        "threshold_db": -18.0,
        "ratio": 4.0,
        "attack_ms": 10.0,
        "release_ms": 100.0,
        "makeup_db": 0.0,
        "mix": 1.0,
    },
    processor=process,
)
