"""Deterministic processing for Prism's ordered stock-effect chains."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import numpy as np

from prism.plugins import (
    STOCK_PLUGINS,
    AutomationCurve,
    AutomationPoint,
    ParameterIdentity,
    Plugin,
    parameter_identity,
)
from prism.stock_plugins.filter import low_pass
from prism.stock_plugins.gain import db_envelope

if TYPE_CHECKING:
    from prism.project.builder import Project, Track


@dataclass(frozen=True, slots=True)
class CompiledParameterEnvelope:
    """One parameter's sparse, absolute automation envelope.

    ``base_value`` is held before the first authored point by the canonical
    policy.  The explicit legacy policy can instead hold the first point.  At
    and after the final point the final value is held.  ``curve`` only governs
    the interval between authored points; it never adds smoothing to a hold
    curve or to a live/discontinuous control.
    """

    identity: ParameterIdentity
    base_value: float
    point_frames: tuple[int, ...]
    point_values: tuple[float, ...]
    curve: AutomationCurve
    pre_first: Literal["base_value", "first_point"]

    @property
    def is_constant(self) -> bool:
        """Whether no authored points require a time-varying envelope."""

        return not self.point_frames

    def value_at(self, frame: int) -> float:
        """Return the exact policy-defined value at one absolute frame."""

        if not self.point_frames:
            return self.base_value
        if frame < self.point_frames[0]:
            return (
                self.base_value
                if self.pre_first == "base_value"
                else self.point_values[0]
            )
        if self.curve == "linear":
            return float(
                np.interp(
                    float(frame),
                    np.asarray(self.point_frames, dtype=np.float64),
                    np.asarray(self.point_values, dtype=np.float64),
                )
            )
        index = int(np.searchsorted(self.point_frames, frame, side="right") - 1)
        return self.point_values[min(index, len(self.point_values) - 1)]

    def values(self, frames: int) -> np.ndarray:
        """Materialize values only when an audio adapter needs samples."""

        if isinstance(frames, bool) or not isinstance(frames, int) or frames < 0:
            raise ValueError("Automation frame count must be a non-negative integer.")
        if self.is_constant:
            return np.full(frames, self.base_value, dtype=np.float64)
        positions = np.arange(frames, dtype=np.int64)
        if self.curve == "linear":
            values = np.interp(
                positions,
                np.asarray(self.point_frames, dtype=np.float64),
                np.asarray(self.point_values, dtype=np.float64),
            )
            if self.pre_first == "base_value":
                values[positions < self.point_frames[0]] = self.base_value
            return np.asarray(values, dtype=np.float64)
        indices = np.searchsorted(self.point_frames, positions, side="right") - 1
        if self.pre_first == "base_value":
            before_first = positions < self.point_frames[0]
            indices = np.clip(indices, 0, len(self.point_values) - 1)
            result = np.asarray(self.point_values, dtype=np.float64)[indices]
            result[before_first] = self.base_value
            return result
        indices = np.clip(indices, 0, len(self.point_values) - 1)
        return np.asarray(self.point_values, dtype=np.float64)[indices]


def compile_parameter_envelope(
    project: Project, plugin: Plugin, parameter: str
) -> CompiledParameterEnvelope:
    """Compile one sparse lane into absolute sample-frame coordinates."""

    identity = parameter_identity(plugin, parameter)
    base = _setting(plugin, parameter)
    matches = [
        lane
        for lane in project.automation_lanes
        if lane.target is plugin
        and lane.parameter_identity.parameter_id == identity.parameter_id
    ]
    if len(matches) > 1:
        raise ValueError(
            f"Plugin parameter {parameter!r} has more than one physical automation lane."
        )
    if not matches:
        return CompiledParameterEnvelope(
            identity=identity,
            base_value=base,
            point_frames=(),
            point_values=(),
            curve="hold",
            pre_first="base_value",
        )
    lane = matches[0]
    return CompiledParameterEnvelope(
        identity=identity,
        base_value=base,
        point_frames=tuple(project.timing.bar_to_frame(point.bar) for point in lane.points),
        point_values=tuple(point.value for point in lane.points),
        curve=lane.curve,
        pre_first=(
            "first_point"
            if project.automation_compatibility == "first_point_v0"
            else "base_value"
        ),
    )


def automation_values(
    project: Project,
    points: tuple[AutomationPoint, ...],
    curve: AutomationCurve,
    base_value: float,
    frames: int,
) -> np.ndarray:
    """Evaluate a non-plugin envelope, such as track output gain."""

    envelope = CompiledParameterEnvelope(
        identity=ParameterIdentity("__anonymous__", "anonymous", "anonymous", "anonymous"),
        base_value=base_value,
        point_frames=tuple(project.timing.bar_to_frame(point.bar) for point in points),
        point_values=tuple(point.value for point in points),
        curve=curve,
        pre_first=(
            "first_point"
            if project.automation_compatibility == "first_point_v0"
            else "base_value"
        ),
    )
    return envelope.values(frames)


def process_track_plugins(project: Project, track: Track, samples: np.ndarray) -> np.ndarray:
    """Apply instrument automation and every effect in insertion order."""

    output = np.asarray(samples, dtype=np.float64).copy()
    instrument = track.instrument_plugin
    if instrument is not None:
        output = _instrument_automation(project, instrument, output)
    return process_effect_chain(project, track.effects, output)


def process_effect_chain(
    project: Project, effects: list[Plugin], samples: np.ndarray
) -> np.ndarray:
    """Apply an ordered effect chain to a track, bus, or master buffer."""

    output = np.asarray(samples, dtype=np.float64).copy()
    for effect in effects:
        if effect.vst3 is not None:
            from prism.vst_host import process_vst3_effect

            output = process_vst3_effect(project, effect, output)
            continue
        parameters = {
            name: parameter_values(project, effect, name, output.shape[0])
            for name in effect.settings
        }
        definition = STOCK_PLUGINS.get("effect", effect.preset)
        if definition.processor is None:
            raise TypeError(f"Stock effect {effect.preset!r} has no audio processor")
        processor = definition.processor
        assert processor is not None
        output = processor(output, parameters, project.sample_rate, project.tempo)
    return np.asarray(output, dtype=np.float64)


def has_automation(project: Project, target: Plugin | None, parameter: str) -> bool:
    """Return whether a plugin parameter has a lane in this project."""

    return target is not None and any(
        lane.target is target and lane.parameter == parameter
        for lane in project.automation_lanes
    )


def _instrument_automation(
    project: Project, instrument: Plugin, samples: np.ndarray
) -> np.ndarray:
    output = samples
    if instrument.vst3 is not None:
        return output
    if instrument.preset != "uniwave" and has_automation(project, instrument, "gain_db"):
        values = parameter_values(project, instrument, "gain_db", output.shape[0])
        base = _setting(instrument, "gain_db")
        output = output * db_envelope(values - base)[:, np.newaxis]
    if instrument.preset != "uniwave" and has_automation(project, instrument, "cutoff_hz"):
        cutoff = parameter_values(project, instrument, "cutoff_hz", output.shape[0])
        output = low_pass(output, cutoff, project.sample_rate)
    return output


def parameter_values(
    project: Project, plugin: Plugin, parameter: str, frames: int
) -> np.ndarray:
    return compile_parameter_envelope(project, plugin, parameter).values(frames)


def _setting(plugin: Plugin, name: str) -> float:
    value = plugin.settings.get(name)
    if value is None and plugin.vst3 is not None:
        # A named declaration and an indexed automation selector can describe
        # the same physical parameter.  Use inspected metadata when available
        # so the canonical envelope has the actual configured base value.
        requested = parameter_identity(plugin, name).parameter_id
        for selector, candidate in plugin.vst3.parameters.items():
            if parameter_identity(plugin, selector).parameter_id == requested:
                value = candidate
                break
    if value is None and plugin.vst3 is not None:
        return 0.0
    if value is None:
        raise TypeError(f"Plugin parameter {name!r} has no base setting")
    if not isinstance(value, int | float):
        raise TypeError(f"Plugin parameter {name!r} is not numeric")
    return float(value)


__all__ = [
    "CompiledParameterEnvelope",
    "automation_values",
    "compile_parameter_envelope",
    "has_automation",
    "parameter_values",
    "process_effect_chain",
    "process_track_plugins",
]
