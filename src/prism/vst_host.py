"""Safe orchestration for isolated VST3 worker processes."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Mapping, Sequence

import numpy as np

from prism.errors import RenderError
from prism.midi import TICKS_PER_BEAT
from prism.music import ControlPoint, Note, note_to_midi
from prism.plugins import Plugin

if TYPE_CHECKING:
    from prism.project.builder import Project


def inspect_vst3(
    project: Project, alias: str, *, state: str | None = None
) -> list[dict[str, object]]:
    """Return the parameters reported by one registered VST3."""

    path, _entry = project.vsts.resolve(alias)
    request: dict[str, object] = {"action": "inspect", "plugin_path": str(path)}
    if state is not None:
        request["state_path"] = str(_project_file(project, state))
    response = _run_worker(request)
    parameters = response.get("parameters")
    if not isinstance(parameters, list):
        raise RenderError("The VST3 worker returned an invalid parameter list.")
    return parameters


def edit_vst3(project: Project, alias: str, state: str) -> Path:
    """Open a plugin editor and persist its state in the project folder."""

    path, _entry = project.vsts.resolve(alias)
    state_path = _project_file(project, state, must_exist=False)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    _run_worker(
        {
            "action": "edit",
            "plugin_path": str(path),
            "state_path": str(state_path),
        }
    )
    return state_path


def render_vst3_instrument(
    project: Project,
    plugin: Plugin,
    notes: Sequence[Note],
    pitch_bend: Sequence[ControlPoint],
    modulation: Sequence[ControlPoint],
    frames: int,
) -> np.ndarray:
    """Render arranged MIDI with one external instrument."""

    with tempfile.TemporaryDirectory(prefix="prism-vst3-") as temporary:
        root = Path(temporary)
        midi_path = root / "notes.mid"
        midi_path.write_bytes(_midi_file(project.tempo, notes, pitch_bend, modulation))
        output_path = root / "output.npy"
        request = _plugin_request(project, plugin)
        request.update(
            {
                "action": "instrument",
                "midi_path": str(midi_path),
                "output_path": str(output_path),
                "sample_rate": project.sample_rate,
                "frames": frames,
                "tempo": project.tempo,
                "automation": _automation_file(project, plugin, frames, root),
            }
        )
        _run_worker(request)
        return _read_output(output_path, frames)


def process_vst3_effect(
    project: Project, plugin: Plugin, samples: np.ndarray
) -> np.ndarray:
    """Process one stereo buffer through an external effect."""

    with tempfile.TemporaryDirectory(prefix="prism-vst3-") as temporary:
        root = Path(temporary)
        input_path = root / "input.npy"
        output_path = root / "output.npy"
        np.save(input_path, np.asarray(samples, dtype=np.float32), allow_pickle=False)
        request = _plugin_request(project, plugin)
        request.update(
            {
                "action": "effect",
                "input_path": str(input_path),
                "output_path": str(output_path),
                "sample_rate": project.sample_rate,
                "frames": samples.shape[0],
                "tempo": project.tempo,
                "automation": _automation_file(
                    project, plugin, samples.shape[0], root
                ),
            }
        )
        _run_worker(request)
        return _read_output(output_path, samples.shape[0])


def _plugin_request(project: Project, plugin: Plugin) -> dict[str, object]:
    if plugin.vst3 is None:
        raise RenderError(f"Plugin {plugin.name!r} is not a VST3 plugin.")
    path, entry = project.vsts.resolve(plugin.vst3.alias)
    request: dict[str, object] = {
        "plugin_path": str(path),
        "plugin_sha256": entry.sha256,
        "parameters": dict(plugin.vst3.parameters),
    }
    if plugin.vst3.state is not None:
        request["state_path"] = str(_project_file(project, plugin.vst3.state))
    if plugin.vst3.preset is not None:
        request["preset_path"] = str(_project_file(project, plugin.vst3.preset))
    return request


def _automation_file(
    project: Project, plugin: Plugin, frames: int, root: Path
) -> str | None:
    from prism.effects import parameter_values

    lanes = [lane for lane in project.automation_lanes if lane.target is plugin]
    if not lanes:
        return None
    arrays = {
        lane.parameter: parameter_values(project, plugin, lane.parameter, frames)
        for lane in lanes
    }
    path = root / "automation.npz"
    np.savez(path, **arrays)  # type: ignore[arg-type]
    return str(path)


def _project_file(
    project: Project, value: str, *, must_exist: bool = True
) -> Path:
    path = (project.root / value).resolve(strict=False)
    try:
        path.relative_to(project.root)
    except ValueError as error:
        raise RenderError("VST state and preset files must stay inside the project.") from error
    if must_exist and not path.is_file():
        raise RenderError(f"VST state or preset file does not exist: {value}")
    return path


def _run_worker(request: Mapping[str, object]) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="prism-vst3-request-") as temporary:
        root = Path(temporary)
        request_path = root / "request.json"
        response_path = root / "response.json"
        request_path.write_text(json.dumps(request), encoding="utf-8")
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "prism.vst_worker",
                str(request_path),
                str(response_path),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or "unknown plugin error"
            raise RenderError(f"VST3 worker failed: {detail}")
        try:
            response = json.loads(response_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise RenderError("VST3 worker returned no readable result.") from error
        if not isinstance(response, dict):
            raise RenderError("VST3 worker returned an invalid result.")
        return response


def _read_output(path: Path, frames: int) -> np.ndarray:
    try:
        samples = np.load(path, allow_pickle=False)
    except (OSError, ValueError) as error:
        raise RenderError("VST3 worker did not return readable audio.") from error
    if samples.ndim != 2 or samples.shape != (frames, 2):
        raise RenderError(
            f"VST3 returned {samples.shape}; Prism requires {frames} stereo frames."
        )
    if not np.isfinite(samples).all():
        raise RenderError("VST3 returned non-finite audio samples.")
    return np.asarray(samples, dtype=np.float64)


def _midi_file(
    tempo: float,
    notes: Sequence[Note],
    bends: Sequence[ControlPoint],
    modulation: Sequence[ControlPoint],
) -> bytes:
    events: list[tuple[int, int, bytes]] = []
    microseconds = int(round(60_000_000 / tempo))
    events.append((0, -3, b"\xff\x51\x03" + microseconds.to_bytes(3, "big")))
    for note in notes:
        start = round(note.start * TICKS_PER_BEAT)
        end = round((note.start + note.duration) * TICKS_PER_BEAT)
        number = note_to_midi(note.pitch)
        events.append((start, 1, bytes((0x90, number, note.velocity))))
        events.append((end, 0, bytes((0x80, number, 0))))
    for point in bends:
        value = max(0, min(16_383, round((point.value + 2.0) / 4.0 * 16_383)))
        events.append(
            (round(point.beat * TICKS_PER_BEAT), -1, bytes((0xE0, value & 0x7F, value >> 7)))
        )
    for point in modulation:
        value = max(0, min(127, round(point.value * 127)))
        events.append((round(point.beat * TICKS_PER_BEAT), -1, bytes((0xB0, 1, value))))
    end_tick = max((tick for tick, _order, _payload in events), default=0)
    events.append((end_tick, 9, b"\xff\x2f\x00"))
    body = bytearray()
    previous = 0
    for tick, _order, payload in sorted(events, key=lambda item: (item[0], item[1])):
        body.extend(_variable_length(tick - previous))
        body.extend(payload)
        previous = tick
    header = b"MThd" + (6).to_bytes(4, "big") + (0).to_bytes(2, "big")
    header += (1).to_bytes(2, "big") + TICKS_PER_BEAT.to_bytes(2, "big")
    return header + b"MTrk" + len(body).to_bytes(4, "big") + bytes(body)


def _variable_length(value: int) -> bytes:
    buffer = value & 0x7F
    result = bytearray((buffer,))
    while value >> 7:
        value >>= 7
        buffer = (value & 0x7F) | 0x80
        result.insert(0, buffer)
    return bytes(result)


__all__ = ["edit_vst3", "inspect_vst3", "process_vst3_effect", "render_vst3_instrument"]
