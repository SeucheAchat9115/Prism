"""Stock lead instrument plugin."""

from prism.plugins import Parameter, PluginDefinition
from prism.synthesis.types import SynthPatch

definition = PluginDefinition(
    preset="lead",
    kind="instrument",
    parameters={
        "gain_db": Parameter(-6.0, -60.0, 12.0),
        "cutoff_hz": Parameter(3_600.0, 20.0, 20_000.0),
    },
    defaults={
        "waveform": "square", "attack_ms": 8.0, "decay_ms": 90.0,
        "sustain": 0.62, "release_ms": 140.0, "cutoff_hz": 3_600.0, "gain_db": -6.0,
    },
    midi_program=81,
    synth_patch=SynthPatch("square", 8.0, 90.0, 0.62, 140.0, 3_600.0, 0.82, 0.30),
    melodic=True,
)
