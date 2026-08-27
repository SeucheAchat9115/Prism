"""Central registry for Prism's built-in instruments and effects."""

from prism.plugins import Parameter, PluginDefinition, PluginRegistry
from prism.stock_plugins import (
    bass,
    chorus,
    compressor,
    delay,
    distortion,
    filter,
    gain,
    lead,
    pad,
    reverb,
    tremolo,
    uniwave,
)

stock_registry = PluginRegistry()

_EFFECTS: tuple[PluginDefinition, ...] = (
    gain.definition,
    filter.definition,
    distortion.definition,
    delay.definition,
    chorus.definition,
    reverb.definition,
    compressor.definition,
    tremolo.definition,
)
for effect in _EFFECTS:
    stock_registry.register(effect)

for instrument in (uniwave.definition, bass.definition, lead.definition, pad.definition):
    stock_registry.register(instrument)

for preset in ("sampler", "audio_player", "kick", "snare", "hihat"):
    stock_registry.register(
        PluginDefinition(
            preset=preset,
            kind="instrument",
            parameters={"gain_db": Parameter(0.0, -60.0, 12.0)},
            defaults={"gain_db": 0.0},
            drum_note={"kick": 36, "snare": 38, "hihat": 42}.get(preset),
        )
    )

__all__ = ["stock_registry"]
