"""Stock bass instrument plugin."""

from prism.plugins import Parameter, PluginDefinition
from prism.synthesis.types import SynthPatch

definition = PluginDefinition(
    preset="bass",
    kind="instrument",
    parameters={
        "gain_db": Parameter(-6.0, -60.0, 12.0),
        "cutoff_hz": Parameter(900.0, 20.0, 20_000.0),
    },
    defaults={
        "waveform": "saw", "attack_ms": 5.0, "decay_ms": 100.0,
        "sustain": 0.58, "release_ms": 110.0, "cutoff_hz": 900.0, "gain_db": -6.0,
    },
    midi_program=38,
    synth_patch=SynthPatch("saw", 5.0, 100.0, 0.58, 110.0, 900.0, 0.78, 0.46),
    melodic=True,
)
