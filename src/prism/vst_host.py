"""Safe orchestration for isolated VST3 worker processes."""

from __future__ import annotations

import json
import math
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping, Sequence, cast

import numpy as np

from prism.arrangement import (
    MIDI_MODULATION_STEPS,
    MIDI_PITCH_BEND_STEPS,
    CompiledTrackEvents,
)
from prism.errors import RenderError
from prism.midi import TICKS_PER_BEAT
from prism.music import ControlPoint, Note, note_to_midi
from prism.plugins import Plugin
from prism.timing import MusicalTiming
from prism.vst import VSTBackendConfig

if TYPE_CHECKING:
    from prism.project.builder import Project


@dataclass(frozen=True)
class VSTParameterChange:
    """One exposed VST3 parameter changed during an editor session."""

    index: int
    name: str
    label: str
    before: float
    after: float


@dataclass(frozen=True)
class VSTEditResult:
    """Saved state and user-visible net changes from a VST3 editor session."""

    state_path: Path
    baseline: str
    state_changed: bool
    parameter_changes: tuple[VSTParameterChange, ...]


@dataclass(frozen=True, slots=True)
class VSTWorkerDiagnostics:
    """Bounded details about a failed or cancelled isolated worker."""

    operation: str
    plugin_alias: str | None
    track: str | None
    last_stage: str
    message: str
    returncode: int | None
    timed_out: bool = False
    cancelled: bool = False
    stdout: str = ""
    stderr: str = ""

    def as_dict(self) -> dict[str, object]:
        """Return diagnostics in a logging- and manifest-friendly shape."""

        return {
            "operation": self.operation,
            "plugin_alias": self.plugin_alias,
            "track": self.track,
            "last_stage": self.last_stage,
            "message": self.message,
            "returncode": self.returncode,
            "timed_out": self.timed_out,
            "cancelled": self.cancelled,
            "stdout": self.stdout,
            "stderr": self.stderr,
        }


class VSTWorkerError(RenderError):
    """A readable worker failure with bounded developer diagnostics."""

    def __init__(self, diagnostics: VSTWorkerDiagnostics) -> None:
        self.diagnostics = diagnostics
        subject = diagnostics.operation or "operation"
        location = (
            f" for plugin {diagnostics.plugin_alias!r}"
            if diagnostics.plugin_alias
            else ""
        )
        track = f" on track {diagnostics.track!r}" if diagnostics.track else ""
        status = "cancelled" if diagnostics.cancelled else (
            "timed out" if diagnostics.timed_out else "failed"
        )
        message = (
            f"VST3 {subject}{location}{track} {status} at stage "
            f"{diagnostics.last_stage}: {diagnostics.message}"
        )
        super().__init__(message)


class _BoundedOutput:
    """Collect worker output without allowing a plugin to exhaust memory."""

    def __init__(self, limit: int) -> None:
        self._limit = limit
        self._data = bytearray()
        self._truncated = False

    def add(self, chunk: bytes) -> None:
        remaining = self._limit - len(self._data)
        if remaining > 0:
            self._data.extend(chunk[:remaining])
        if len(chunk) > max(remaining, 0):
            self._truncated = True

    def text(self) -> str:
        value = bytes(self._data).decode("utf-8", errors="replace")
        if self._truncated:
            value += "\n[… worker output truncated …]"
        return value


def inspect_vst3(
    project: Project,
    alias: str,
    *,
    state: str | None = None,
    cancel_event: threading.Event | None = None,
) -> list[dict[str, object]]:
    """Return the parameters reported by one registered VST3."""

    path, _entry = project.vsts.resolve(alias)
    request: dict[str, object] = {
        "action": "inspect",
        "plugin_path": str(path),
        "plugin_alias": alias,
        "backend": project.vst_backend.as_dict(),
    }
    if state is not None:
        request["state_path"] = str(_project_file(project, state))
    response = _invoke_worker(request, cancel_event=cancel_event)
    parameters = response.get("parameters")
    if not isinstance(parameters, list):
        raise RenderError("The VST3 worker returned an invalid parameter list.")
    return parameters


def edit_vst3(
    project: Project,
    alias: str,
    state: str,
    *,
    cancel_event: threading.Event | None = None,
    timeout_seconds: float | None = None,
) -> VSTEditResult:
    """Open a plugin editor and persist its state in the project folder."""

    path, _entry = project.vsts.resolve(alias)
    state_path = _project_file(project, state, must_exist=False)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    response = _invoke_worker(
        {
            "action": "edit",
            "plugin_path": str(path),
            "state_path": str(state_path),
            "plugin_alias": alias,
            "backend": project.vst_backend.as_dict(),
        },
        cancel_event=cancel_event,
        timeout_seconds=timeout_seconds,
    )
    baseline = response.get("baseline")
    state_changed = response.get("state_changed")
    raw_changes = response.get("parameter_changes")
    if baseline not in {"plugin_defaults", "saved_state"}:
        raise RenderError("The VST3 editor returned an invalid comparison baseline.")
    if not isinstance(state_changed, bool) or not isinstance(raw_changes, list):
        raise RenderError("The VST3 editor returned an invalid change summary.")
    changes: list[VSTParameterChange] = []
    try:
        for item in raw_changes:
            if not isinstance(item, dict):
                raise TypeError
            changes.append(
                VSTParameterChange(
                    index=int(item["index"]),
                    name=str(item["name"]),
                    label=str(item.get("label", "")),
                    before=float(item["before"]),
                    after=float(item["after"]),
                )
            )
    except (KeyError, TypeError, ValueError) as error:
        raise RenderError("The VST3 editor returned invalid parameter changes.") from error
    return VSTEditResult(
        state_path=state_path,
        baseline=str(baseline),
        state_changed=state_changed,
        parameter_changes=tuple(changes),
    )


def render_vst3_instrument(
    project: Project,
    plugin: Plugin,
    notes: Sequence[Note] | CompiledTrackEvents,
    pitch_bend: Sequence[ControlPoint] | int = (),
    modulation: Sequence[ControlPoint] = (),
    frames: int | None = None,
    *,
    cancel_event: threading.Event | None = None,
    timeout_seconds: float | None = None,
) -> np.ndarray:
    """Render MIDI with one external instrument.

    New callers pass a :class:`CompiledTrackEvents` stream and the frame count
    as the fourth positional argument. The original note/controller signature
    remains accepted for plugins and user code that call this low-level helper.
    """

    stream: CompiledTrackEvents | None
    if isinstance(notes, CompiledTrackEvents):
        stream = notes
        if isinstance(pitch_bend, int) and frames is None:
            frames = pitch_bend
        elif not isinstance(pitch_bend, int):
            raise RenderError("Compiled VST events need the output frame count.")
    else:
        stream = None
    if frames is None:
        raise RenderError("VST instrument rendering needs an output frame count.")

    with tempfile.TemporaryDirectory(prefix="prism-vst3-") as temporary:
        root = Path(temporary)
        midi_path = root / "notes.mid"
        if stream is not None:
            midi_payload = _midi_file(project.timing, stream)
        else:
            assert not isinstance(notes, CompiledTrackEvents)
            assert not isinstance(pitch_bend, int)
            midi_payload = _midi_file(project.timing, notes, pitch_bend, modulation)
        midi_path.write_bytes(midi_payload)
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
                "backend": project.vst_backend.as_dict(),
            }
        )
        _invoke_worker(
            request,
            cancel_event=cancel_event,
            timeout_seconds=timeout_seconds,
        )
        return _read_output(output_path, frames)


def process_vst3_effect(
    project: Project,
    plugin: Plugin,
    samples: np.ndarray,
    *,
    cancel_event: threading.Event | None = None,
    timeout_seconds: float | None = None,
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
                "backend": project.vst_backend.as_dict(),
            }
        )
        _invoke_worker(
            request,
            cancel_event=cancel_event,
            timeout_seconds=timeout_seconds,
        )
        return _read_output(output_path, samples.shape[0])


def _plugin_request(project: Project, plugin: Plugin) -> dict[str, object]:
    if plugin.vst3 is None:
        raise RenderError(f"Plugin {plugin.name!r} is not a VST3 plugin.")
    path, entry = project.vsts.resolve(plugin.vst3.alias)
    request: dict[str, object] = {
        "plugin_path": str(path),
        "plugin_sha256": entry.sha256,
        "parameters": dict(plugin.vst3.parameters),
        "plugin_alias": plugin.vst3.alias,
        "track": plugin.track,
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
    arrays: dict[str, np.ndarray] = {}
    identities: dict[str, str] = {}
    for lane in lanes:
        identity = lane.parameter_identity
        selector = identity.selector if identity.index is not None else lane.parameter
        previous = identities.get(identity.parameter_id)
        if previous is not None:
            raise RenderError(
                f"Automation selectors {previous!r} and {lane.parameter!r} target the "
                f"same physical VST parameter {identity.parameter_id!r}."
            )
        identities[identity.parameter_id] = lane.parameter
        arrays[selector] = parameter_values(project, plugin, lane.parameter, frames)
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


def _invoke_worker(
    request: Mapping[str, object],
    *,
    cancel_event: threading.Event | None = None,
    timeout_seconds: float | None = None,
) -> dict[str, object]:
    """Call the worker while retaining compatibility with simple test doubles."""

    if cancel_event is None and timeout_seconds is None:
        return _run_worker(request)
    return _run_worker(
        request,
        cancel_event=cancel_event,
        timeout_seconds=timeout_seconds,
    )


def _run_worker(
    request: Mapping[str, object],
    *,
    cancel_event: threading.Event | None = None,
    timeout_seconds: float | None = None,
) -> dict[str, object]:
    """Run one isolated worker with bounded output and process-tree cleanup."""

    action = str(request.get("action", "unknown"))
    config = _backend_config(request)
    timeout = (
        _default_worker_timeout(action, config)
        if timeout_seconds is None
        else _positive_timeout(timeout_seconds)
    )
    with tempfile.TemporaryDirectory(prefix="prism-vst3-request-") as temporary:
        root = Path(temporary)
        request_path = root / "request.json"
        response_path = root / "response.json"
        request_path.write_text(json.dumps(dict(request)), encoding="utf-8")
        process = _start_worker(request_path, response_path)
        stdout = _BoundedOutput(config.diagnostic_limit)
        stderr = _BoundedOutput(config.diagnostic_limit)
        readers = (
            _drain_output(process.stdout, stdout),
            _drain_output(process.stderr, stderr),
        )
        deadline = None if timeout is None else time.monotonic() + timeout
        cancelled = False
        timed_out = False
        while process.poll() is None:
            if cancel_event is not None and cancel_event.is_set():
                cancelled = True
                break
            if deadline is not None and time.monotonic() >= deadline:
                timed_out = True
                break
            time.sleep(0.02)
        if cancelled or timed_out:
            _terminate_process_tree(process)
        try:
            returncode = process.wait(timeout=2.0)
        except (subprocess.TimeoutExpired, TimeoutError):
            _terminate_process_tree(process, force=True)
            polled = process.poll()
            returncode = -9 if polled is None else polled
        for reader in readers:
            reader.join(timeout=1.0)
        stdout_text = stdout.text()
        stderr_text = stderr.text()

        if cancelled or timed_out or returncode != 0:
            diagnostic = _worker_diagnostics(
                request,
                returncode=returncode,
                stdout=stdout_text,
                stderr=stderr_text,
                timed_out=timed_out,
                cancelled=cancelled,
            )
            raise VSTWorkerError(diagnostic)
        try:
            response = json.loads(response_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            diagnostic = _worker_diagnostics(
                request,
                returncode=returncode,
                stdout=stdout_text,
                stderr=stderr_text,
                message="worker returned no readable result",
            )
            raise VSTWorkerError(diagnostic) from error
        if not isinstance(response, dict):
            diagnostic = _worker_diagnostics(
                request,
                returncode=returncode,
                stdout=stdout_text,
                stderr=stderr_text,
                message="worker returned an invalid result",
            )
            raise VSTWorkerError(diagnostic)
        return response


def _backend_config(request: Mapping[str, object]) -> VSTBackendConfig:
    raw = request.get("backend")
    if not isinstance(raw, Mapping):
        return VSTBackendConfig()
    values = dict(raw)
    try:
        return VSTBackendConfig(
            render_block_size=int(values.get("render_block_size", 512)),
            inspection_timeout_seconds=float(
                values.get("inspection_timeout_seconds", 30.0)
            ),
            load_timeout_seconds=float(values.get("load_timeout_seconds", 30.0)),
            render_timeout_seconds=float(values.get("render_timeout_seconds", 120.0)),
            edit_timeout_seconds=(
                None
                if values.get("edit_timeout_seconds") is None
                else float(values["edit_timeout_seconds"])
            ),
            diagnostic_limit=int(values.get("diagnostic_limit", 8_192)),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise RenderError("The VST backend configuration is invalid.") from error


def _default_worker_timeout(action: str, config: VSTBackendConfig) -> float | None:
    if action == "inspect":
        return config.load_timeout_seconds + config.inspection_timeout_seconds
    if action == "edit":
        return config.edit_timeout_seconds
    return config.load_timeout_seconds + config.render_timeout_seconds


def _positive_timeout(value: float) -> float:
    if not math.isfinite(value) or value <= 0.0:
        raise RenderError("VST worker timeout must be positive and finite.")
    return float(value)


def _start_worker(request_path: Path, response_path: Path) -> subprocess.Popen[bytes]:
    command = [
        sys.executable,
        "-m",
        "prism.vst_worker",
        str(request_path),
        str(response_path),
    ]
    if os.name == "nt":
        return subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        )
    return subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )


def _drain_output(stream: object, sink: _BoundedOutput) -> threading.Thread:
    def drain() -> None:
        if stream is None or not hasattr(stream, "read"):
            return
        reader = cast(Any, stream)
        while True:
            chunk = reader.read(4096)
            if not chunk:
                return
            if isinstance(chunk, str):
                chunk = chunk.encode("utf-8", errors="replace")
            sink.add(bytes(chunk))

    thread = threading.Thread(target=drain, name="prism-vst3-worker-output", daemon=True)
    thread.start()
    return thread


def _terminate_process_tree(process: subprocess.Popen[bytes], *, force: bool = False) -> None:
    """Stop a worker and descendants without leaving an orphaned plugin host."""

    if os.name == "nt":
        if process.poll() is None:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        return
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGKILL if force else signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        try:
            (process.kill if force else process.terminate)()
        except (ProcessLookupError, OSError):
            pass


def _worker_diagnostics(
    request: Mapping[str, object],
    *,
    returncode: int | None,
    stdout: str,
    stderr: str,
    timed_out: bool = False,
    cancelled: bool = False,
    message: str | None = None,
) -> VSTWorkerDiagnostics:
    parsed = _parse_worker_diagnostic(stderr)
    operation = str(parsed.get("operation", request.get("action", "unknown")))
    alias_value = parsed.get("plugin_alias", request.get("plugin_alias"))
    track_value = parsed.get("track", request.get("track"))
    last_stage = str(parsed.get("last_stage", "worker_exit"))
    detail = message or str(parsed.get("message", "unknown plugin error"))
    return VSTWorkerDiagnostics(
        operation=operation,
        plugin_alias=None if alias_value is None else str(alias_value),
        track=None if track_value is None else str(track_value),
        last_stage=last_stage,
        message=detail,
        returncode=returncode,
        timed_out=timed_out,
        cancelled=cancelled,
        stdout=stdout,
        stderr=stderr,
    )


def _parse_worker_diagnostic(stderr: str) -> dict[str, object]:
    marker = "PRISM_VST_DIAGNOSTIC:"
    for line in stderr.splitlines():
        if not line.startswith(marker):
            continue
        try:
            value = json.loads(line[len(marker) :])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return {}


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
    tempo: float | MusicalTiming,
    notes: Sequence[Note] | CompiledTrackEvents,
    bends: Sequence[ControlPoint] = (),
    modulation: Sequence[ControlPoint] = (),
    *,
    pitch_bend_range: float = 2.0,
) -> bytes:
    timing = tempo if isinstance(tempo, MusicalTiming) else MusicalTiming(tempo_bpm=tempo)
    if isinstance(notes, CompiledTrackEvents):
        return _compiled_midi_file(notes, timing)
    events: list[tuple[int, int, bytes]] = []
    microseconds = timing.microseconds_per_quarter_note
    events.append((0, -3, b"\xff\x51\x03" + microseconds.to_bytes(3, "big")))
    for note in notes:
        start = timing.quarter_notes_to_ticks(note.start, TICKS_PER_BEAT)
        end = timing.quarter_notes_to_ticks(
            note.start + note.duration, TICKS_PER_BEAT
        )
        number = note_to_midi(note.pitch)
        events.append((start, 1, bytes((0x90, number, note.velocity))))
        events.append((end, 0, bytes((0x80, number, 0))))
    for point in bends:
        events.append(
            (
                timing.quarter_notes_to_ticks(point.beat, TICKS_PER_BEAT),
                -1,
                _pitch_bend_message(0, point.value, pitch_bend_range),
            )
        )
    for point in modulation:
        value = max(0, min(127, round(point.value * 127)))
        events.append(
            (
                timing.quarter_notes_to_ticks(point.beat, TICKS_PER_BEAT),
                -1,
                bytes((0xB0, 1, value)),
            )
        )
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


def _compiled_midi_file(stream: CompiledTrackEvents, timing: MusicalTiming) -> bytes:
    """Serialize one compiled stream with explicit equal-time event ordering."""

    events: list[tuple[int, int, int, bytes]] = []
    microseconds = timing.microseconds_per_quarter_note
    events.append((0, -3, -1, b"\xff\x51\x03" + microseconds.to_bytes(3, "big")))
    for event in stream.events:
        if event.kind not in {"note_on", "note_off"}:
            continue
        assert event.midi_note is not None
        tick = timing.quarter_notes_to_ticks(event.beat, TICKS_PER_BEAT)
        status = 0x90 if event.kind == "note_on" else 0x80
        velocity = event.velocity if event.velocity is not None else 0
        events.append(
            (
                tick,
                0 if event.kind == "note_off" else 5,
                event.sequence,
                bytes((status, event.midi_note, velocity)),
            )
        )
    for controller in stream.midi_controller_events(TICKS_PER_BEAT):
        if controller.controller == "pitch_bend":
            payload = _pitch_bend_message(0, controller.value, controller.pitch_bend_range)
            order = 3
        else:
            value = max(0, min(MIDI_MODULATION_STEPS, round(controller.value * 127.0)))
            payload = bytes((0xB0, 1, value))
            order = 4
        events.append((controller.tick, order, controller.sequence, payload))
    end_tick = max(
        timing.quarter_notes_to_ticks(stream.total_beats, TICKS_PER_BEAT),
        max((tick for tick, _order, _sequence, _payload in events), default=0),
    )
    events.append((end_tick, 9, 2**31 - 1, b"\xff\x2f\x00"))
    body = bytearray()
    previous = 0
    for tick, _order, _sequence, payload in sorted(events, key=lambda item: item[:3]):
        body.extend(_variable_length(tick - previous))
        body.extend(payload)
        previous = tick
    header = b"MThd" + (6).to_bytes(4, "big") + (0).to_bytes(2, "big")
    header += (1).to_bytes(2, "big") + TICKS_PER_BEAT.to_bytes(2, "big")
    return header + b"MTrk" + len(body).to_bytes(4, "big") + bytes(body)


def _pitch_bend_message(channel: int, semitones: float, bend_range: float = 2.0) -> bytes:
    if not math.isfinite(bend_range) or bend_range <= 0.0:
        raise RenderError("VST pitch-bend range must be positive and finite.")
    value = min(
        MIDI_PITCH_BEND_STEPS,
        max(0, round(8_192 + semitones / bend_range * 8_191)),
    )
    return bytes((0xE0 | channel, value & 0x7F, (value >> 7) & 0x7F))


def _variable_length(value: int) -> bytes:
    buffer = value & 0x7F
    result = bytearray((buffer,))
    while value >> 7:
        value >>= 7
        buffer = (value & 0x7F) | 0x80
        result.insert(0, buffer)
    return bytes(result)


__all__ = [
    "VSTEditResult",
    "VSTParameterChange",
    "VSTWorkerDiagnostics",
    "VSTWorkerError",
    "edit_vst3",
    "inspect_vst3",
    "process_vst3_effect",
    "render_vst3_instrument",
]
