"""Stock pad instrument plugin."""

from prism.plugins import Parameter, PluginDefinition
from prism.synthesis.types import SynthPatch

definition = PluginDefinition(
    preset="pad",
    kind="instrument",
    parameters={
        "gain_db": Parameter(-6.0, -60.0, 12.0),
        "cutoff_hz": Parameter(2_400.0, 20.0, 20_000.0),
    },
    defaults={
        "waveform": "triangle", "attack_ms": 180.0, "decay_ms": 380.0,
        "sustain": 0.76, "release_ms": 420.0, "cutoff_hz": 2_400.0, "gain_db": -6.0,
    },
    midi_program=89,
    synth_patch=SynthPatch("triangle", 180.0, 380.0, 0.76, 420.0, 2_400.0, 0.92, 0.26),
    melodic=True,
)
