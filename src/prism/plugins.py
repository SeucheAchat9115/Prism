"""Stock instrument/effect plugins and readable parameter automation."""

from __future__ import annotations

import math
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Callable, Literal, Mapping, Sequence

from prism.errors import ProjectError
from prism.synthesis.types import SynthPatch
from prism.vst import VST3, canonical_vst_parameter

PluginKind = Literal["instrument", "effect"]
AutomationCurve = Literal["linear", "hold"]
AutomationCompatibility = Literal["initial_value_v1", "first_point_v0"]
EffectPreset = str

CANONICAL_AUTOMATION_VERSION: AutomationCompatibility = "initial_value_v1"
LEGACY_AUTOMATION_VERSION: AutomationCompatibility = "first_point_v0"

if TYPE_CHECKING:
    import numpy as np

    from prism.synthesis.types import NativeSynthSpec

    Processor = Callable[
        [np.ndarray, Mapping[str, "np.ndarray"], int, float], np.ndarray
    ]
    SynthProcessor = Callable[["NativeSynthSpec", int, float, float], np.ndarray]
else:
    Processor = Callable[..., object]
    SynthProcessor = Callable[..., object]


@dataclass(frozen=True, slots=True)
class Parameter:
    """One numeric plugin parameter and its accepted range."""

    default: float
    minimum: float
    maximum: float


@dataclass(frozen=True, slots=True)
class PluginDefinition:
    """Registry entry shared by the authoring, renderer, and MIDI layers."""

    preset: str
    kind: PluginKind
    parameters: Mapping[str, Parameter]
    defaults: Mapping[str, object]
    processor: Processor | None = None
    midi_program: int | None = None
    synth_patch: SynthPatch | None = None
    melodic: bool = False
    drum_note: int | None = None
    synth_processor: SynthProcessor | None = None


class PluginRegistry:
    """Validated catalog of stock instruments and effects."""

    def __init__(self) -> None:
        self._definitions: dict[tuple[PluginKind, str], PluginDefinition] = {}

    def register(self, definition: PluginDefinition) -> None:
        key = (definition.kind, definition.preset)
        if key in self._definitions:
            raise ProjectError(f"Plugin {definition.preset!r} is already registered.")
        if definition.kind == "effect" and definition.processor is None:
            raise ProjectError(f"Effect {definition.preset!r} needs an audio processor.")
        self._definitions[key] = definition

    def get(self, kind: PluginKind, preset: str) -> PluginDefinition:
        try:
            return self._definitions[(kind, preset)]
        except KeyError as error:
            available = ", ".join(sorted(self.presets(kind))) or "none"
            raise ProjectError(
                f"Unknown stock {kind} plugin {preset!r}. Available: {available}."
            ) from error

    def presets(self, kind: PluginKind) -> frozenset[str]:
        return frozenset(
            preset for entry_kind, preset in self._definitions if entry_kind == kind
        )


class _StockPluginRegistryProxy:
    """Lazy proxy that avoids importing stock modules during model loading."""

    @staticmethod
    def _registry() -> PluginRegistry:
        from prism.stock_plugins.registry import stock_registry

        return stock_registry

    def register(self, definition: PluginDefinition) -> None:
        self._registry().register(definition)

    def get(self, kind: PluginKind, preset: str) -> PluginDefinition:
        return self._registry().get(kind, preset)

    def presets(self, kind: PluginKind) -> frozenset[str]:
        return self._registry().presets(kind)


STOCK_PLUGINS = _StockPluginRegistryProxy()


@dataclass(frozen=True, slots=True)
class Plugin:
    """A stock or external instrument/effect in one signal chain."""

    name: str
    track: str
    kind: PluginKind
    preset: str
    settings: Mapping[str, object]
    automatable: Mapping[str, Parameter]
    vst3: VST3 | None = None
    instance_id: str | None = None

    def __str__(self) -> str:
        return f"{self.track} → {self.name} ({self.preset} {self.kind})"

    @property
    def stable_instance_id(self) -> str:
        """Return the compiled identity of this concrete plugin instance."""

        return self.instance_id or f"{self.track}:{self.kind}:{self.name}"


@dataclass(frozen=True, slots=True)
class AutomationPoint:
    """A plugin parameter value at an absolute song position in bars."""

    bar: float
    value: float


@dataclass(frozen=True, slots=True)
class AutomationLane:
    """A named sequence of values controlling one plugin parameter."""

    name: str
    target: Plugin
    parameter: str
    points: tuple[AutomationPoint, ...]
    curve: AutomationCurve

    @property
    def parameter_identity(self) -> "ParameterIdentity":
        """Resolve the lane to the target's current physical parameter identity."""

        return parameter_identity(self.target, self.parameter)

    def __str__(self) -> str:
        return f"{self.name}: {self.target.name}.{self.parameter} ({len(self.points)} points)"


@dataclass(frozen=True, slots=True)
class OutputGainLane:
    """One explicit, shared post-instrument gain envelope for a track."""

    name: str
    points: tuple[AutomationPoint, ...]
    curve: AutomationCurve

    def __str__(self) -> str:
        return f"{self.name}: shared track output gain ({len(self.points)} points)"


@dataclass(frozen=True, slots=True)
class ParameterIdentity:
    """Stable identity plus readable selector for one plugin parameter."""

    instance_id: str
    parameter_id: str
    selector: str
    display_name: str
    index: int | None = None


def parameter_identity(target: Plugin, parameter_name: str) -> ParameterIdentity:
    """Return a canonical identity without discarding the authored selector."""

    instance_id = target.stable_instance_id
    if target.vst3 is None:
        clean = str(parameter_name).strip()
        return ParameterIdentity(
            instance_id=instance_id,
            parameter_id=f"stock:{clean}",
            selector=clean,
            display_name=clean,
        )
    try:
        resolved = canonical_vst_parameter(parameter_name, target.vst3.parameter_metadata)
    except ValueError as error:
        raise ProjectError(str(error)) from error
    return ParameterIdentity(
        instance_id=instance_id,
        parameter_id=f"vst3:{resolved.parameter_id}",
        selector=resolved.selector,
        display_name=resolved.name,
        index=resolved.index,
    )


def effect_plugin(
    preset: EffectPreset,
    *,
    name: str,
    track: str,
    settings: Mapping[str, float],
    instance_id: str | None = None,
) -> Plugin:
    """Validate and create one stock effect plugin."""

    definition = STOCK_PLUGINS.get("effect", preset)
    parameters = definition.parameters
    unknown = sorted(set(settings) - set(parameters))
    if unknown:
        raise ProjectError(
            f"Effect {preset!r} has no parameter named {', '.join(unknown)}."
        )
    resolved = {
        parameter_name: _parameter_value(
            settings.get(parameter_name, parameter.default),
            parameter,
            f"Effect {name!r} {parameter_name}",
        )
        for parameter_name, parameter in parameters.items()
    }
    return Plugin(
        name=name,
        track=track,
        kind="effect",
        preset=preset,
        settings=MappingProxyType(resolved),
        automatable=MappingProxyType(parameters),
        instance_id=instance_id,
    )


def instrument_plugin(
    preset: str,
    *,
    name: str,
    track: str,
    settings: Mapping[str, object],
    melodic: bool,
    instance_id: str | None = None,
) -> Plugin:
    """Create the public plugin view of a built-in instrument."""

    definition = STOCK_PLUGINS.get("instrument", preset)
    gain_db = settings["gain_db"]
    assert isinstance(gain_db, int | float)
    automatable = dict(definition.parameters)
    if preset == "uniwave":
        for parameter_name, value in settings.items():
            if parameter_name.startswith("wave_") and parameter_name.endswith(
                ("_level", "_detune_cents")
            ) and isinstance(value, int | float):
                if parameter_name.endswith("_level"):
                    automatable[parameter_name] = Parameter(float(value), 0.0, 1.0)
                else:
                    automatable[parameter_name] = Parameter(float(value), -100.0, 100.0)
    if melodic and "cutoff_hz" not in automatable:
        cutoff_hz = settings["cutoff_hz"]
        assert isinstance(cutoff_hz, int | float)
        automatable["cutoff_hz"] = Parameter(float(cutoff_hz), 20.0, 20_000.0)
    return Plugin(
        name=name,
        track=track,
        kind="instrument",
        preset=preset,
        settings=MappingProxyType(dict(settings)),
        automatable=MappingProxyType(automatable),
        instance_id=instance_id,
    )


def automation_points(
    values: Sequence[tuple[float, float]],
    *,
    target: Plugin,
    parameter_name: str,
) -> tuple[AutomationPoint, ...]:
    """Validate producer-authored ``(bar, value)`` automation points.

    Bar positions are converted to quarter-note beats by the owning project's
    timing map when the lane is scheduled; this layer only validates the
    producer-facing bar coordinate and plugin value.
    """

    parameter = target.automatable.get(parameter_name)
    if parameter is None and target.vst3 is not None:
        parameter = Parameter(0.0, 0.0, 1.0)
    if parameter is None:
        available = ", ".join(target.automatable) or "none"
        raise ProjectError(
            f"Plugin {target.name!r} parameter {parameter_name!r} cannot be automated. "
            f"Automatable parameters: {available}."
        )
    if target.vst3 is not None:
        # With cached inspect metadata this rejects unknown/ambiguous names at
        # authoring time.  Without it, the isolated worker repeats the same
        # check against the live plugin before loading audio into its graph.
        parameter_identity(target, parameter_name)
    if not values:
        raise ProjectError("Automation needs at least one (bar, value) point.")
    points: list[AutomationPoint] = []
    previous = -1.0
    for bar, value in values:
        if not math.isfinite(bar) or bar < 0.0:
            raise ProjectError("Automation point bars must be finite and zero or greater.")
        if bar <= previous:
            raise ProjectError("Automation point bars must be in strictly increasing order.")
        resolved = _parameter_value(
            value,
            parameter,
            f"Automation for {target.name!r} {parameter_name}",
        )
        points.append(AutomationPoint(float(bar), resolved))
        previous = bar
    return tuple(points)


def output_gain_points(
    values: Sequence[tuple[float, float]], *, label: str
) -> tuple[AutomationPoint, ...]:
    """Validate producer-authored output-gain points expressed in dB."""

    if not values:
        raise ProjectError("Output gain needs at least one (bar, value) point.")
    points: list[AutomationPoint] = []
    previous = -1.0
    for bar, value in values:
        if not math.isfinite(bar) or bar < 0.0:
            raise ProjectError("Output-gain point bars must be finite and zero or greater.")
        if bar <= previous:
            raise ProjectError("Output-gain point bars must be in strictly increasing order.")
        if not math.isfinite(value) or not -60.0 <= value <= 12.0:
            raise ProjectError(f"{label} values must be between -60 and +12 dB.")
        points.append(AutomationPoint(float(bar), float(value)))
        previous = bar
    return tuple(points)


def vst3_plugin(
    specification: VST3,
    *,
    name: str,
    track: str,
    kind: PluginKind,
    instance_id: str | None = None,
) -> Plugin:
    """Bind a producer-authored VST3 declaration to a Prism signal chain."""

    parameters = {
        parameter_name: Parameter(value, 0.0, 1.0)
        for parameter_name, value in specification.parameters.items()
    }
    return Plugin(
        name=name,
        track=track,
        kind=kind,
        preset=specification.alias,
        settings=MappingProxyType(dict(specification.parameters)),
        automatable=MappingProxyType(parameters),
        vst3=specification,
        instance_id=instance_id,
    )


def _parameter_value(value: float, parameter: Parameter, label: str) -> float:
    resolved = float(value)
    if not math.isfinite(resolved) or not parameter.minimum <= resolved <= parameter.maximum:
        raise ProjectError(
            f"{label} must be between {parameter.minimum:g} and {parameter.maximum:g}."
        )
    return resolved


__all__ = [
    "AutomationLane",
    "AutomationPoint",
    "AutomationCompatibility",
    "CANONICAL_AUTOMATION_VERSION",
    "EffectPreset",
    "LEGACY_AUTOMATION_VERSION",
    "OutputGainLane",
    "Parameter",
    "ParameterIdentity",
    "Plugin",
    "PluginDefinition",
    "PluginRegistry",
    "STOCK_PLUGINS",
    "parameter_identity",
    "vst3_plugin",
    "output_gain_points",
]
