"""Internal DawDreamer worker used to isolate third-party VST3 plugins."""

from __future__ import annotations

import json
import math
import sys
import threading
import time
from pathlib import Path
from typing import Any, Mapping

import numpy as np


def main(arguments: list[str] | None = None) -> int:
    args = sys.argv[1:] if arguments is None else arguments
    if len(args) != 2:
        print("This internal command expects a request and response file.", file=sys.stderr)
        return 2
    request_path, response_path = map(Path, args)
    try:
        request = json.loads(request_path.read_text(encoding="utf-8"))
        response = _execute(request)
        response_path.write_text(json.dumps(response), encoding="utf-8")
        return 0
    except Exception as error:  # plugin/backend exceptions must stay in this process
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        return 1


def _execute(request: Mapping[str, Any]) -> dict[str, object]:
    _enable_windows_dpi_awareness()
    try:
        import dawdreamer as daw
    except ImportError as error:
        raise RuntimeError(
            "VST3 support is not installed. Run: uv sync --extra vst3"
        ) from error

    action = str(request["action"])
    sample_rate = int(request.get("sample_rate", 44_100))
    engine = daw.RenderEngine(sample_rate, 512)
    if hasattr(engine, "set_bpm"):
        engine.set_bpm(float(request.get("tempo", 120.0)))
    plugin = engine.make_plugin_processor("prism_vst3", str(request["plugin_path"]))
    if action == "edit":
        state_path = Path(str(request["state_path"]))
        previous_state = state_path.read_bytes() if state_path.is_file() else None
        if previous_state is not None:
            _succeeded(plugin.load_state(str(state_path)), "load the VST3 state")
        before = _parameters(plugin)
        _open_editor_while_processing(engine, plugin)
        _succeeded(plugin.save_state(str(state_path)), "save the VST3 state")
        after = _parameters(plugin)
        return {
            "state_path": str(state_path),
            "baseline": "saved_state" if previous_state is not None else "plugin_defaults",
            "state_changed": previous_state != state_path.read_bytes(),
            "parameter_changes": _parameter_changes(before, after),
        }
    _load_state(plugin, request)
    parameters = _parameters(plugin)

    if action == "inspect":
        return {"parameters": parameters}
    if action not in {"instrument", "effect"}:
        raise ValueError(f"Unknown VST3 worker action: {action}")

    _set_parameters(plugin, parameters, request.get("parameters", {}))
    _set_automation(plugin, parameters, request.get("automation"))
    frames = int(request["frames"])
    latency = _latency(plugin)
    duration = (frames + latency) / sample_rate
    if action == "instrument":
        _succeeded(plugin.load_midi(str(request["midi_path"])), "load the MIDI file")
        engine.load_graph([(plugin, [])])
    elif action == "effect":
        audio = np.load(str(request["input_path"]), allow_pickle=False)
        padded = np.pad(audio, ((0, latency), (0, 0))).T.astype(np.float32)
        playback = engine.make_playback_processor("prism_input", padded)
        engine.load_graph([(playback, []), (plugin, [playback.get_name()])])
    _succeeded(engine.render(duration), "render the VST3 graph")
    output = np.asarray(plugin.get_audio(), dtype=np.float32).T
    if output.ndim != 2:
        raise RuntimeError(f"Plugin returned invalid audio shape {output.shape}.")
    if output.shape[1] == 1:
        output = np.repeat(output, 2, axis=1) / np.sqrt(2.0)
    elif output.shape[1] != 2:
        raise RuntimeError("Prism currently supports mono or stereo VST3 output only.")
    output = output[latency : latency + frames]
    if output.shape[0] < frames:
        output = np.pad(output, ((0, frames - output.shape[0]), (0, 0)))
    np.save(str(request["output_path"]), output, allow_pickle=False)
    return {"frames": frames, "latency_samples": latency}


def _enable_windows_dpi_awareness() -> None:
    """Opt the worker into crisp, correctly scaled third-party windows."""

    if sys.platform != "win32":
        return
    try:
        import ctypes

        user32 = ctypes.windll.user32
        if hasattr(user32, "SetProcessDpiAwarenessContext"):
            # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
            if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
                return
        try:
            shcore = ctypes.windll.shcore
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
    plugin: Any, descriptions: list[dict[str, object]], values: object
) -> None:
    if not isinstance(values, dict):
        raise ValueError("VST3 parameters must be an object.")
    for selector, value in values.items():
        _succeeded(
            plugin.set_parameter(
                _parameter_index(str(selector), descriptions), float(value)
            ),
            f"set VST3 parameter {selector!r}",
        )


def _set_automation(
    plugin: Any, descriptions: list[dict[str, object]], path: object
) -> None:
    if not path:
        return
    with np.load(str(path), allow_pickle=False) as arrays:
        for selector in arrays.files:
            _succeeded(
                plugin.set_automation(
                    _parameter_index(selector, descriptions),
                    np.asarray(arrays[selector], dtype=np.float32),
                ),
                f"automate VST3 parameter {selector!r}",
            )


def _parameter_index(selector: str, descriptions: list[dict[str, object]]) -> int:
    if selector.startswith("#"):
        raw = selector[1:].split(":", 1)[0]
        try:
            requested = int(raw)
        except ValueError as error:
            raise ValueError(f"Invalid indexed VST parameter selector {selector!r}.") from error
        if any(_description_index(item) == requested for item in descriptions):
            return requested
        raise ValueError(f"VST parameter index #{requested} does not exist.")
    matches = [
        _description_index(item)
        for item in descriptions
        if str(item["name"]).casefold() == selector.casefold()
    ]
    if not matches:
        raise ValueError(
            f"VST parameter {selector!r} does not exist. Run prism plugins inspect."
        )
    if len(matches) > 1:
        raise ValueError(
            f"VST parameter {selector!r} is ambiguous; use '#INDEX: Name' from inspect."
        )
    return matches[0]


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
