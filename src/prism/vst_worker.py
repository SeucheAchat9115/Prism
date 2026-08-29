"""Internal DawDreamer worker used to isolate third-party VST3 plugins."""

from __future__ import annotations

import json
import sys
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
        if state_path.is_file():
            _succeeded(plugin.load_state(str(state_path)), "load the VST3 state")
        plugin.open_editor()
        _succeeded(plugin.save_state(str(state_path)), "save the VST3 state")
        return {"state_path": str(state_path)}
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


def _load_state(plugin: Any, request: Mapping[str, Any]) -> None:
    state = request.get("state_path")
    preset = request.get("preset_path")
    if state:
        _succeeded(plugin.load_state(str(state)), "load the VST3 state")
    elif preset:
        _succeeded(plugin.load_vst3_preset(str(preset)), "load the VST3 preset")


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
