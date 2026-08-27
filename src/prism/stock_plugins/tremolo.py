"""Stock stereo tremolo effect plugin."""

from typing import Mapping

import numpy as np

from prism.plugins import Parameter, PluginDefinition


def process(
    samples: np.ndarray, parameters: Mapping[str, np.ndarray], sample_rate: int, tempo: float
) -> np.ndarray:
    """Modulate left and right channel levels with a sine oscillator."""

    del tempo
    phase = np.cumsum(2.0 * np.pi * parameters["rate_hz"] / sample_rate)
    offset = np.deg2rad(parameters["stereo_phase_deg"])
    depth = parameters["depth"]
    gain_left = 1.0 - depth * (0.5 + 0.5 * np.sin(phase))
    gain_right = 1.0 - depth * (0.5 + 0.5 * np.sin(phase + offset))
    wet = samples * np.column_stack((gain_left, gain_right))
    mix = parameters["mix"][:, np.newaxis]
    return np.asarray(samples * (1.0 - mix) + wet * mix, dtype=np.float64)


definition = PluginDefinition(
    preset="tremolo",
    kind="effect",
    parameters={
        "rate_hz": Parameter(5.0, 0.05, 20.0),
        "depth": Parameter(0.6, 0.0, 1.0),
        "stereo_phase_deg": Parameter(0.0, 0.0, 180.0),
        "mix": Parameter(1.0, 0.0, 1.0),
    },
    defaults={"rate_hz": 5.0, "depth": 0.6, "stereo_phase_deg": 0.0, "mix": 1.0},
    processor=process,
)
