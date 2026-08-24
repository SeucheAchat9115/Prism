"""Isolated optional Pedalboard host, executed as ``python -m prism.plugins.worker``."""

from __future__ import annotations

import base64
import sys
from dataclasses import dataclass
from multiprocessing import shared_memory
from pathlib import Path
from typing import Any

import numpy as np
from pydantic import ValidationError

from prism.plugins.protocol import WorkerFailure, WorkerRequest, WorkerResponse


@dataclass(slots=True)
class _Instance:
    plugin: Any
    bypassed: bool


class _Host:
    def __init__(self) -> None:
        self.instances: dict[str, _Instance] = {}

    @staticmethod
    def _pedalboard() -> tuple[Any, Any, Any]:
        try:
            import pedalboard
        except ImportError as error:
            raise RuntimeError(
                "The optional plugin host is not installed; run `uv sync --extra plugins`."
            ) from error
        return (
            getattr(pedalboard, "Pedalboard"),
            getattr(pedalboard, "VST3Plugin"),
            getattr(pedalboard, "load_plugin"),
        )

    def probe(self, params: dict[str, Any]) -> dict[str, Any]:
        _, vst3_plugin, load_plugin = self._pedalboard()
        path = str(Path(_string(params, "path")).resolve(strict=True))
        names = _plugin_names(vst3_plugin, path)
        plugins: list[dict[str, str]] = []
        for identifier in names:
            plugin = _load(load_plugin, path, identifier)
            plugins.append(
                {
                    "plugin_identifier": identifier,
                    "name": str(
                        getattr(plugin, "descriptive_name", None)
                        or getattr(plugin, "name", None)
                        or identifier
                    ),
                    "manufacturer": str(
                        getattr(plugin, "manufacturer_name", None) or "Unknown"
                    ),
                    "version": str(getattr(plugin, "version", None) or "Unknown"),
                    "category": str(getattr(plugin, "category", None) or "Effect"),
                }
            )
        return {"plugins": plugins}

    def load(self, params: dict[str, Any]) -> dict[str, Any]:
        _, _, load_plugin = self._pedalboard()
        instance_id = _string(params, "instance_id")
        path = str(Path(_string(params, "path")).resolve(strict=True))
        identifier = _string(params, "plugin_identifier")
        plugin = _load(load_plugin, path, identifier)
        state = params.get("state")
        if isinstance(state, str):
            plugin.raw_state = base64.b64decode(state, validate=True)
        parameters = params.get("parameters", {})
        if not isinstance(parameters, dict):
            raise ValueError("parameters must be an object")
        for parameter_id, raw_value in parameters.items():
            _set_parameter(plugin, str(parameter_id), float(raw_value))
        self.instances[instance_id] = _Instance(plugin, bool(params.get("bypassed", False)))
        return {"parameters": _parameters(plugin)}

    def parameters(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"parameters": _parameters(self._instance(params).plugin)}

    def set_parameter(self, params: dict[str, Any]) -> dict[str, Any]:
        instance = self._instance(params)
        _set_parameter(
            instance.plugin,
            _string(params, "parameter_id"),
            float(params["raw_value"]),
        )
        return {}

    def set_bypass(self, params: dict[str, Any]) -> dict[str, Any]:
        self._instance(params).bypassed = bool(params["bypassed"])
        return {}

    def get_state(self, params: dict[str, Any]) -> dict[str, Any]:
        state = bytes(self._instance(params).plugin.raw_state)
        max_bytes = int(params["max_bytes"])
        if max_bytes < 0:
            raise ValueError("max_bytes must not be negative")
        if len(state) > max_bytes:
            raise ValueError("Plugin state exceeds the configured limit")
        return {"state": base64.b64encode(state).decode("ascii")}

    def unload(self, params: dict[str, Any]) -> dict[str, Any]:
        self.instances.pop(_string(params, "instance_id"), None)
        return {}

    def process(self, params: dict[str, Any]) -> dict[str, Any]:
        instance = self._instance(params)
        frames = int(params["frames"])
        channels = int(params["channels"])
        sample_rate = int(params["sample_rate"])
        memory = shared_memory.SharedMemory(name=_string(params, "shared_memory"))
        try:
            target = np.ndarray((frames, channels), dtype=np.float32, buffer=memory.buf)
            if instance.bypassed:
                return {}
            audio = np.ascontiguousarray(target.T)
            result = instance.plugin.process(
                audio,
                sample_rate,
                reset=bool(params.get("reset", False)),
            )
            rendered = np.asarray(result, dtype=np.float32)
            if rendered.shape == (channels, frames):
                rendered = rendered.T
            if rendered.shape != target.shape:
                raise ValueError(
                    f"Plugin returned shape {rendered.shape}; expected {target.shape}"
                )
            target[:] = rendered
        finally:
            memory.close()
        return {}

    def _instance(self, params: dict[str, Any]) -> _Instance:
        instance_id = _string(params, "instance_id")
        try:
            return self.instances[instance_id]
        except KeyError as error:
            raise ValueError(f"Plugin instance is not loaded: {instance_id}") from error


def _plugin_names(vst3_plugin: Any, path: str) -> list[str]:
    getter = getattr(vst3_plugin, "get_plugin_names_for_file", None)
    if getter is None:
        return [Path(path).stem]
    names = [str(value) for value in getter(path)]
    return names or [Path(path).stem]


def _load(load_plugin: Any, path: str, identifier: str) -> Any:
    try:
        return load_plugin(path, plugin_name=identifier)
    except TypeError:
        return load_plugin(path)


def _parameters(plugin: Any) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    parameters = getattr(plugin, "parameters", {})
    for parameter_id, parameter in parameters.items():
        values.append(
            {
                "id": str(parameter_id),
                "name": str(getattr(parameter, "name", None) or parameter_id),
                "raw_value": float(parameter.raw_value),
                "value": str(getattr(parameter, "string_value", None) or ""),
            }
        )
    return values


def _set_parameter(plugin: Any, parameter_id: str, raw_value: float) -> None:
    if not 0.0 <= raw_value <= 1.0:
        raise ValueError("raw_value must be between 0 and 1")
    parameters = getattr(plugin, "parameters", {})
    try:
        parameters[parameter_id].raw_value = raw_value
    except KeyError as error:
        raise ValueError(f"Plugin parameter does not exist: {parameter_id}") from error


def _string(params: dict[str, Any], key: str) -> str:
    value = params.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _response(request_id: str, result: dict[str, Any]) -> WorkerResponse:
    return WorkerResponse(request_id=request_id, ok=True, result=result)


def _error(request_id: str, error: Exception) -> WorkerResponse:
    unavailable = isinstance(error, RuntimeError) and "optional plugin host" in str(error)
    return WorkerResponse(
        request_id=request_id,
        ok=False,
        error=WorkerFailure(
            code="host_unavailable" if unavailable else "worker_error",
            message=str(error),
        ),
    )


def main() -> int:
    host = _Host()
    handlers = {
        "probe": host.probe,
        "load": host.load,
        "parameters": host.parameters,
        "set_parameter": host.set_parameter,
        "set_bypass": host.set_bypass,
        "get_state": host.get_state,
        "unload": host.unload,
        "process": host.process,
    }
    for line in sys.stdin:
        request_id = "unknown"
        try:
            request = WorkerRequest.model_validate_json(line)
            request_id = request.request_id
            if request.method == "ping":
                response = _response(request_id, {"ready": True})
            elif request.method == "shutdown":
                response = _response(request_id, {})
                print(response.model_dump_json(), flush=True)
                return 0
            else:
                handler = handlers.get(request.method)
                if handler is None:
                    raise ValueError(f"Unknown worker method: {request.method}")
                response = _response(request_id, handler(request.params))
        except (ValidationError, ValueError, RuntimeError, OSError, KeyError) as error:
            response = _error(request_id, error)
        except Exception as error:  # defensive isolation boundary
            response = _error(request_id, RuntimeError(f"Plugin host failed: {error}"))
        print(response.model_dump_json(), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
