"""Built-in deterministic drum and melodic synthesis."""

from prism.synthesis.engine import (
    MAX_SYNTH_SECONDS,
    NativeSynthRender,
    native_synth_presets,
    render_native_synth,
)
from prism.synthesis.types import (
    MELODIC_PRESETS,
    PERCUSSION_PRESETS,
    NativeSynthPresetInfo,
    NativeSynthSpec,
    SynthKind,
    SynthPreset,
    SynthWaveform,
    default_sequence,
    note_frequency,
)

__all__ = [
    "MAX_SYNTH_SECONDS",
    "MELODIC_PRESETS",
    "PERCUSSION_PRESETS",
    "NativeSynthPresetInfo",
    "NativeSynthRender",
    "NativeSynthSpec",
    "SynthKind",
    "SynthPreset",
    "SynthWaveform",
    "default_sequence",
    "native_synth_presets",
    "note_frequency",
    "render_native_synth",
]
