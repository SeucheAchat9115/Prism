"""Internal DawDreamer worker used to isolate third-party VST3 plugins."""

from __future__ import annotations

import json
import math
import os
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from prism.vst import CanonicalVSTParameter, canonical_vst_parameter


def main(arguments: list[str] | None = None) -> int:
    args = sys.argv[1:] if arguments is None else arguments
    if len(args) != 2:
        print("This internal command expects a request and response file.", file=sys.stderr)
        return 2
    request_path, response_path = map(Path, args)
    request: dict[str, Any] = {}
    stage = "read_request"
    try:
        request = json.loads(request_path.read_text(encoding="utf-8"))
        if not isinstance(request, dict):
            raise ValueError("VST3 worker request must be an object.")
        _set_stage(request, "request_loaded")
        response = _execute(request)
        _set_stage(request, "response_written")
        response_path.write_text(json.dumps(response), encoding="utf-8")
        return 0
    except Exception as error:  # plugin/backend exceptions must stay in this process
        stage = str(request.get("_last_stage", stage)) if isinstance(request, dict) else stage
        context = request if isinstance(request, dict) else {}
        diagnostic = {
            "operation": str(context.get("action", "unknown")),
            "plugin_alias": context.get("plugin_alias"),
            "track": context.get("track"),
            "last_stage": stage,
            "error_type": type(error).__name__,
            "message": str(error),
        }
        print(f"PRISM_VST_DIAGNOSTIC:{json.dumps(diagnostic, sort_keys=True)}", file=sys.stderr)
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        return 1


def _execute(request: Mapping[str, Any]) -> dict[str, object]:
    _set_stage(request, "backend_import")
    _enable_windows_dpi_awareness()
    try:
        import dawdreamer as daw
    except ImportError as error:
        raise RuntimeError(
            "VST3 support is not installed. Run: uv sync --extra vst3"
        ) from error

    action = str(request["action"])
    sample_rate = int(request.get("sample_rate", 44_100))
    block_size = _validated_block_size(request.get("backend"))
    engine = daw.RenderEngine(sample_rate, block_size)
    _set_stage(request, "engine_created")
    if hasattr(engine, "set_bpm"):
        engine.set_bpm(float(request.get("tempo", 120.0)))
    plugin = engine.make_plugin_processor("prism_vst3", str(request["plugin_path"]))
    _set_stage(request, "plugin_loaded")
    if action == "edit":
        state_path = Path(str(request["state_path"]))
        previous_state = state_path.read_bytes() if state_path.is_file() else None
        if previous_state is not None:
            _succeeded(plugin.load_state(str(state_path)), "load the VST3 state")
            _set_stage(request, "state_loaded")
        before = _parameters(plugin)
        _set_stage(request, "parameters_inspected")
        _open_editor_while_processing(engine, plugin)
        _set_stage(request, "editor_closed")
        _save_state_atomically(plugin, state_path)
        _set_stage(request, "state_saved")
        after = _parameters(plugin)
        response: dict[str, object] = {
            "state_path": str(state_path),
            "baseline": "saved_state" if previous_state is not None else "plugin_defaults",
            "state_changed": previous_state != _read_state(state_path),
            "parameter_changes": _parameter_changes(before, after),
        }
        if "backend" in request:
            response["backend"] = _backend_metadata(daw, plugin, block_size)
        return response
    _load_state(plugin, request)
    _set_stage(request, "state_or_preset_loaded")
    parameters = _parameters(plugin)
    _set_stage(request, "parameters_inspected")

    if action == "inspect":
        return {"parameters": parameters}
    if action not in {"instrument", "effect"}:
        raise ValueError(f"Unknown VST3 worker action: {action}")

    requested_parameters = request.get("parameters", {})
    automation_path = request.get("automation")
    parameter_selectors = _parameter_selectors(requested_parameters)
    automation_selectors = _automation_selectors(automation_path)
    targets = {
        **_resolve_parameter_targets(parameter_selectors, parameters),
        **_resolve_parameter_targets(automation_selectors, parameters),
    }
    _set_parameters(plugin, requested_parameters, targets)
    _set_stage(request, "parameters_applied")
    _set_automation(plugin, automation_path, targets)
    _set_stage(request, "automation_applied")
    frames = int(request["frames"])
    latency = _latency(plugin)
    duration = (frames + latency) / sample_rate
    if action == "instrument":
        _succeeded(plugin.load_midi(str(request["midi_path"])), "load the MIDI file")
        _set_stage(request, "graph_loaded")
        engine.load_graph([(plugin, [])])
    elif action == "effect":
        audio = np.load(str(request["input_path"]), allow_pickle=False)
        _validate_input_audio(audio, frames)
        padded = np.pad(audio, ((0, latency), (0, 0))).T.astype(np.float32)
        playback = engine.make_playback_processor("prism_input", padded)
        engine.load_graph([(playback, []), (plugin, [playback.get_name()])])
        _set_stage(request, "graph_loaded")
    _succeeded(engine.render(duration), "render the VST3 graph")
    _set_stage(request, "graph_rendered")
    output = np.asarray(plugin.get_audio(), dtype=np.float32).T
    if output.ndim != 2:
        raise RuntimeError(f"Plugin returned invalid audio shape {output.shape}.")
    if output.shape[1] == 1:
        output = np.repeat(output, 2, axis=1) / np.sqrt(2.0)
    elif output.shape[1] != 2:
        raise RuntimeError("Prism currently supports mono or stereo VST3 output only.")
    if output.shape[0] < latency + frames:
        raise RuntimeError(
            f"Plugin returned {output.shape[0]} frames; expected at least {latency + frames}."
        )
    output = output[latency : latency + frames]
    if not np.isfinite(output).all():
        raise RuntimeError("Plugin returned non-finite audio samples.")
    _set_stage(request, "audio_validated")
    np.save(str(request["output_path"]), output, allow_pickle=False)
    response = {
        "frames": frames,
        "latency_samples": latency,
    }
    if "backend" in request:
        response["backend"] = _backend_metadata(daw, plugin, block_size)
    return response


def _set_stage(request: Mapping[str, Any], stage: str) -> None:
    """Keep the last completed boundary available if the backend fails."""

    if isinstance(request, dict):
        request["_last_stage"] = stage


def _validated_block_size(raw_backend: object) -> int:
    if not isinstance(raw_backend, Mapping):
        return 512
    value = raw_backend.get("render_block_size", 512)
    if isinstance(value, bool) or not isinstance(value, int) or not 16 <= value <= 8_192:
        raise ValueError("VST render block size must be an integer between 16 and 8192.")
    return value


def _backend_metadata(daw: Any, plugin: Any, block_size: int) -> dict[str, object]:
    """Report backend capabilities separately from plugin capabilities."""

    backend_capabilities = {
        "render_engine": hasattr(daw, "RenderEngine"),
        "plugin_processor": hasattr(daw.RenderEngine, "make_plugin_processor"),
        "playback_processor": hasattr(daw.RenderEngine, "make_playback_processor"),
    }
    plugin_capabilities = {
        "state_load": hasattr(plugin, "load_state"),
        "state_save": hasattr(plugin, "save_state"),
        "preset_load": hasattr(plugin, "load_vst3_preset"),
        "parameter_automation": hasattr(plugin, "set_automation"),
        "latency_query": hasattr(plugin, "get_latency_samples"),
        "editor": hasattr(plugin, "open_editor"),
        "midi": hasattr(plugin, "load_midi"),
    }
    version = getattr(daw, "__version__", None)
    return {
        "name": "dawdreamer",
        "version": None if version is None else str(version),
        "render_block_size": block_size,
        "backend_capabilities": backend_capabilities,
        "plugin_capabilities": plugin_capabilities,
    }


def _validate_input_audio(audio: np.ndarray, frames: int) -> None:
    if audio.ndim != 2 or audio.shape != (frames, 2):
        raise RuntimeError(
            f"Input audio has shape {audio.shape}; Prism requires {frames} stereo frames."
        )
    if not np.isfinite(audio).all():
        raise RuntimeError("Input audio contains non-finite samples.")


def _read_state(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as error:
        raise RuntimeError(f"Saved VST3 state is not readable: {path}") from error


def _save_state_atomically(plugin: Any, state_path: Path) -> None:
    """Save to a sibling temporary file before replacing the previous state."""

    state_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{state_path.name}.", suffix=".tmp", dir=state_path.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        _succeeded(plugin.save_state(str(temporary)), "save the VST3 state")
        _read_state(temporary)
        with temporary.open("r+b") as stream:
            stream.seek(0, 2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, state_path)
    finally:
        temporary.unlink(missing_ok=True)


def _is_windows_platform() -> bool:
    return sys.platform == "win32"


def _enable_windows_dpi_awareness() -> None:
    """Opt the worker into crisp, correctly scaled third-party windows."""

    if not _is_windows_platform():
        return
    try:
        import ctypes

        windll: Any = getattr(ctypes, "windll", None)
        if windll is None:
            return
        user32 = windll.user32
        if hasattr(user32, "SetProcessDpiAwarenessContext"):
            # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
            if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
                return
        try:
            shcore = windll.shcore
            if hasattr(shcore, "SetProcessDpiAwareness"):
                # PROCESS_PER_MONITOR_DPI_AWARE
                if shcore.SetProcessDpiAwareness(2) in (0, None):
                    return
        except (AttributeError, OSError):
            pass
        if hasattr(user32, "SetProcessDPIAware"):
            user32.SetProcessDPIAware()
    except (AttributeError, OSError, TypeError, ValueError):
        # DPI setup is best-effort on older Windows versions and Wine.
        pass


def _open_editor_while_processing(engine: Any, plugin: Any) -> None:
    """Keep the VST active while its blocking editor runs on the UI thread."""

    engine.load_graph([(plugin, [])])
    stop = threading.Event()
    started = threading.Event()
    failure: list[BaseException] = []

    def process_silence() -> None:
        try:
            while not stop.is_set():
                began = time.monotonic()
                _succeeded(engine.render(0.05), "process the VST3 editor graph")
                started.set()
                remaining = 0.05 - (time.monotonic() - began)
                if remaining > 0:
                    stop.wait(remaining)
        except BaseException as error:
            failure.append(error)
            started.set()

    thread = threading.Thread(
        target=process_silence,
        name="prism-vst3-editor-audio",
        daemon=True,
    )
    thread.start()
    started.wait(timeout=5.0)
    try:
        if failure:
            raise failure[0]
        plugin.open_editor()
    finally:
        stop.set()
        thread.join(timeout=5.0)
    if thread.is_alive():
        raise RuntimeError("The VST3 editor audio thread did not stop.")
    if failure:
        raise failure[0]


def _load_state(plugin: Any, request: Mapping[str, Any]) -> None:
    state = request.get("state_path")
    preset = request.get("preset_path")
    if state:
        _succeeded(plugin.load_state(str(state)), "load the VST3 state")
    elif preset:
        _succeeded(plugin.load_vst3_preset(str(preset)), "load the VST3 preset")


def _parameter_changes(
    before: list[dict[str, object]], after: list[dict[str, object]]
) -> list[dict[str, object]]:
    """Describe net exposed-parameter changes made in an editor session."""

    previous = {_description_index(item): item for item in before}
    changes: list[dict[str, object]] = []
    for current in after:
        index = _description_index(current)
        original = previous.get(index)
        if original is None:
            continue
        old_value = float(str(original["value"]))
        new_value = float(str(current["value"]))
        if math.isclose(old_value, new_value, rel_tol=0.0, abs_tol=1e-7):
            continue
        changes.append(
            {
                "index": index,
                "name": str(current["name"]),
                "label": str(current.get("label", "")),
                "before": old_value,
                "after": new_value,
            }
        )
    return changes


def _parameters(plugin: Any) -> list[dict[str, object]]:
    if hasattr(plugin, "get_parameters_description"):
        raw = plugin.get_parameters_description()
        if isinstance(raw, list):
            result: list[dict[str, object]] = []
            for index, item in enumerate(raw):
                values = item if isinstance(item, dict) else {}
                resolved_index = int(values.get("index", index))
                result.append(
                    {
                        "index": resolved_index,
                        "name": str(
                            values.get("name", plugin.get_parameter_name(resolved_index))
                        ),
                        "label": str(values.get("label", "")),
                        "value": float(plugin.get_parameter(resolved_index)),
                        "steps": int(
                            values.get("numSteps", values.get("steps", 0)) or 0
                        ),
                    }
                )
            return result
    count = int(plugin.get_plugin_parameter_size())
    return [
        {
            "index": index,
            "name": str(plugin.get_parameter_name(index)),
            "label": "",
            "value": float(plugin.get_parameter(index)),
            "steps": 0,
        }
        for index in range(count)
    ]


def _set_parameters(
    plugin: Any,
    values: object,
    targets: Mapping[str, CanonicalVSTParameter],
) -> None:
    if not isinstance(values, dict):
        raise ValueError("VST3 parameters must be an object.")
    for selector, value in values.items():
        clean_selector = str(selector)
        _succeeded(
            plugin.set_parameter(targets[clean_selector].index, float(value)),
            f"set VST3 parameter {selector!r}",
        )


def _set_automation(
    plugin: Any,
    path: object,
    targets: Mapping[str, CanonicalVSTParameter],
) -> None:
    if not path:
        return
    with np.load(str(path), allow_pickle=False) as arrays:
        for selector in arrays.files:
            _succeeded(
                plugin.set_automation(
                    targets[selector].index,
                    np.asarray(arrays[selector], dtype=np.float32),
                ),
                f"automate VST3 parameter {selector!r}",
            )


def _parameter_index(selector: str, descriptions: list[dict[str, object]]) -> int:
    target = canonical_vst_parameter(selector, descriptions)
    if target.index is None:
        raise ValueError(f"VST parameter {selector!r} has no inspected index.")
    return target.index


def _parameter_selectors(values: object) -> list[str]:
    if not isinstance(values, dict):
        raise ValueError("VST3 parameters must be an object.")
    return [str(selector) for selector in values]


def _automation_selectors(path: object) -> list[str]:
    if not path:
        return []
    with np.load(str(path), allow_pickle=False) as arrays:
        return list(arrays.files)


def _resolve_parameter_targets(
    selectors: list[str], descriptions: list[dict[str, object]]
) -> dict[str, CanonicalVSTParameter]:
    """Resolve and de-duplicate every request before audio processing."""

    targets: dict[str, CanonicalVSTParameter] = {}
    by_identity: dict[str, str] = {}
    for selector in selectors:
        if selector in targets:
            raise ValueError(f"VST parameter selector {selector!r} is duplicated.")
        target = canonical_vst_parameter(selector, descriptions)
        previous = by_identity.get(target.parameter_id)
        if previous is not None:
            raise ValueError(
                f"VST parameter selectors {previous!r} and {selector!r} target the "
                f"same physical parameter #{target.index}; keep one lane."
            )
        if target.index is None:
            raise ValueError(f"VST parameter {selector!r} has no inspected index.")
        targets[selector] = target
        by_identity[target.parameter_id] = selector
    return targets


def _description_index(description: Mapping[str, object]) -> int:
    value = description["index"]
    if not isinstance(value, int):
        raise ValueError("VST3 returned an invalid parameter index.")
    return value


def _latency(plugin: Any) -> int:
    if not hasattr(plugin, "get_latency_samples"):
        return 0
    latency: int = int(plugin.get_latency_samples())
    return max(0, latency)


def _succeeded(result: object, action: str) -> None:
    if result is False:
        raise RuntimeError(f"Could not {action}.")


if __name__ == "__main__":
    raise SystemExit(main())
