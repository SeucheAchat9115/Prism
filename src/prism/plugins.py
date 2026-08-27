"""Stock instrument/effect plugins and readable parameter automation."""

from __future__ import annotations

import math
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, Mapping, Sequence

from prism.errors import ProjectError

PluginKind = Literal["instrument", "effect"]
AutomationCurve = Literal["linear", "hold"]
EffectPreset = Literal["gain", "filter", "distortion", "delay"]


@dataclass(frozen=True, slots=True)
class Parameter:
    """One numeric plugin parameter and its accepted range."""

    default: float
    minimum: float
    maximum: float


_EFFECT_PARAMETERS: dict[str, dict[str, Parameter]] = {
    "gain": {"gain_db": Parameter(0.0, -60.0, 12.0)},
    "filter": {
        "cutoff_hz": Parameter(1_200.0, 20.0, 20_000.0),
        "mix": Parameter(1.0, 0.0, 1.0),
    },
    "distortion": {
        "drive_db": Parameter(12.0, 0.0, 36.0),
        "mix": Parameter(0.5, 0.0, 1.0),
    },
    "delay": {
        "time_beats": Parameter(0.5, 0.03125, 4.0),
        "feedback": Parameter(0.25, 0.0, 0.95),
        "mix": Parameter(0.2, 0.0, 1.0),
    },
}


@dataclass(frozen=True, slots=True)
class Plugin:
    """A stock instrument or effect in one track's signal chain."""

    name: str
    track: str
    kind: PluginKind
    preset: str
    settings: Mapping[str, object]
    automatable: Mapping[str, Parameter]

    def __str__(self) -> str:
        return f"{self.track} → {self.name} ({self.preset} {self.kind})"


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

    def __str__(self) -> str:
        return f"{self.name}: {self.target.name}.{self.parameter} ({len(self.points)} points)"


def effect_plugin(
    preset: EffectPreset,
    *,
    name: str,
    track: str,
    settings: Mapping[str, float],
) -> Plugin:
    """Validate and create one stock effect plugin."""

    if preset not in _EFFECT_PARAMETERS:
        raise ProjectError("Stock effects are gain, filter, distortion, or delay.")
    parameters = _EFFECT_PARAMETERS[preset]
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
    )


def instrument_plugin(
    preset: str,
    *,
    name: str,
    track: str,
    settings: Mapping[str, object],
    melodic: bool,
) -> Plugin:
    """Create the public plugin view of a built-in instrument."""

    gain_db = settings["gain_db"]
    assert isinstance(gain_db, int | float)
    automatable = {"gain_db": Parameter(float(gain_db), -60.0, 12.0)}
    if melodic:
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
    )


def automation_points(
    values: Sequence[tuple[float, float]],
    *,
    target: Plugin,
    parameter_name: str,
) -> tuple[AutomationPoint, ...]:
    """Validate producer-authored ``(bar, value)`` automation points."""

    parameter = target.automatable.get(parameter_name)
    if parameter is None:
        available = ", ".join(target.automatable) or "none"
        raise ProjectError(
            f"Plugin {target.name!r} parameter {parameter_name!r} cannot be automated. "
            f"Automatable parameters: {available}."
        )
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


def _parameter_value(value: float, parameter: Parameter, label: str) -> float:
    resolved = float(value)
    if not math.isfinite(resolved) or not parameter.minimum <= resolved <= parameter.maximum:
        raise ProjectError(
            f"{label} must be between {parameter.minimum:g} and {parameter.maximum:g}."
        )
    return resolved


__all__ = ["AutomationLane", "AutomationPoint", "EffectPreset", "Plugin"]
