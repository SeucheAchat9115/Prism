"""Deterministic processing for Prism's ordered stock-effect chains."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from prism.plugins import STOCK_PLUGINS, Plugin
from prism.stock_plugins.filter import low_pass
from prism.stock_plugins.gain import db_envelope

if TYPE_CHECKING:
    from prism.project.builder import Project, Track


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
    base = _setting(plugin, parameter)
    lane = next(
        (
            candidate
            for candidate in project.automation_lanes
            if candidate.target is plugin and candidate.parameter == parameter
        ),
        None,
    )
    if lane is None:
        return np.full(frames, base, dtype=np.float64)
    point_frames = np.asarray(
        [point.bar * project.frames_per_bar for point in lane.points], dtype=np.float64
    )
    point_values = np.asarray([point.value for point in lane.points], dtype=np.float64)
    positions = np.arange(frames, dtype=np.float64)
    if lane.curve == "linear":
        return np.interp(positions, point_frames, point_values)
    indices = np.searchsorted(point_frames, positions, side="right") - 1
    indices = np.clip(indices, 0, len(point_values) - 1)
    return np.asarray(point_values[indices], dtype=np.float64)


def _setting(plugin: Plugin, name: str) -> float:
    value = plugin.settings.get(name)
    if value is None and plugin.vst3 is not None:
        return 0.0
    if value is None:
        raise TypeError(f"Plugin parameter {name!r} has no base setting")
    if not isinstance(value, int | float):
        raise TypeError(f"Plugin parameter {name!r} is not numeric")
    return float(value)


__all__ = ["has_automation", "parameter_values", "process_effect_chain", "process_track_plugins"]
