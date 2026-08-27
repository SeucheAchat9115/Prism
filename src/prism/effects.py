"""Deterministic processing for Prism's ordered stock-effect chains."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from prism.plugins import Plugin

if TYPE_CHECKING:
    from prism.project.builder import Project, Track


def process_track_plugins(project: Project, track: Track, samples: np.ndarray) -> np.ndarray:
    """Apply instrument automation and every effect in insertion order."""

    output = np.asarray(samples, dtype=np.float64).copy()
    instrument = track.instrument_plugin
    if instrument is not None:
        output = _instrument_automation(project, instrument, output)
    for effect in track.effects:
        parameters = {
            name: _parameter_values(project, effect, name, output.shape[0])
            for name in effect.settings
        }
        if effect.preset == "gain":
            output *= _db_envelope(parameters["gain_db"])[:, np.newaxis]
        elif effect.preset == "filter":
            wet = _low_pass(output, parameters["cutoff_hz"], project.sample_rate)
            output = _blend(output, wet, parameters["mix"])
        elif effect.preset == "distortion":
            drive = _db_envelope(parameters["drive_db"])
            wet = np.tanh(output * drive[:, np.newaxis]) / np.tanh(
                np.maximum(drive[:, np.newaxis], 1.0)
            )
            output = _blend(output, wet, parameters["mix"])
        elif effect.preset == "delay":
            wet = _delay(
                output,
                time_beats=parameters["time_beats"],
                feedback=parameters["feedback"],
                sample_rate=project.sample_rate,
                tempo=project.tempo,
            )
            output = _blend(output, wet, parameters["mix"])
        else:
            raise TypeError(f"Stock effect {effect.preset!r} has no audio processor")
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
    if has_automation(project, instrument, "gain_db"):
        values = _parameter_values(project, instrument, "gain_db", output.shape[0])
        base = _setting(instrument, "gain_db")
        output = output * _db_envelope(values - base)[:, np.newaxis]
    if has_automation(project, instrument, "cutoff_hz"):
        cutoff = _parameter_values(project, instrument, "cutoff_hz", output.shape[0])
        output = _low_pass(output, cutoff, project.sample_rate)
    return output


def _parameter_values(
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
    value = plugin.settings[name]
    if not isinstance(value, int | float):
        raise TypeError(f"Plugin parameter {name!r} is not numeric")
    return float(value)


def _db_envelope(values: np.ndarray) -> np.ndarray:
    return np.asarray(np.power(10.0, values / 20.0), dtype=np.float64)


def _blend(dry: np.ndarray, wet: np.ndarray, mix: np.ndarray) -> np.ndarray:
    amount = mix[:, np.newaxis]
    return np.asarray(dry * (1.0 - amount) + wet * amount, dtype=np.float64)


def _low_pass(samples: np.ndarray, cutoff: np.ndarray, sample_rate: int) -> np.ndarray:
    limited = np.clip(cutoff, 20.0, sample_rate * 0.45)
    alpha = 1.0 - np.exp(-2.0 * np.pi * limited / sample_rate)
    output = np.empty_like(samples)
    state = np.zeros(2, dtype=np.float64)
    for index in range(samples.shape[0]):
        state += alpha[index] * (samples[index] - state)
        output[index] = state
    return output


def _delay(
    samples: np.ndarray,
    *,
    time_beats: np.ndarray,
    feedback: np.ndarray,
    sample_rate: int,
    tempo: float,
) -> np.ndarray:
    output = np.zeros_like(samples)
    frames_per_beat = sample_rate * 60.0 / tempo
    delays = np.maximum(1, np.rint(time_beats * frames_per_beat).astype(np.int64))
    for index in range(samples.shape[0]):
        source = index - int(delays[index])
        if source >= 0:
            output[index] = samples[source] + output[source] * feedback[index]
    return np.asarray(output, dtype=np.float64)


__all__ = ["has_automation", "process_track_plugins"]
