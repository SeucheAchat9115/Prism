from __future__ import annotations

import base64
import io
import json
import sys
from multiprocessing import shared_memory
from pathlib import Path

import numpy as np
import pytest

from prism.plugins import PluginWorkerClient, PluginWorkerTimeoutError
from prism.plugins import worker as worker_module
from prism.plugins.protocol import WorkerRequest


class _Parameter:
    def __init__(self, name: str, raw_value: float) -> None:
        self.name = name
        self.raw_value = raw_value

    @property
    def string_value(self) -> str:
        return f"{self.raw_value:.2f}"


class _Plugin:
    descriptive_name = "Test Gain"
    manufacturer_name = "Prism Tests"
    version = "1.0"
    category = "Fx"

    def __init__(self) -> None:
        self.parameters = {"gain": _Parameter("Gain", 0.25)}
        self.raw_state = b"initial"
        self.process_calls: list[tuple[int, bool]] = []

    def process(self, audio, sample_rate, *, reset=False):
        self.process_calls.append((sample_rate, reset))
        return np.asarray(audio, dtype=np.float32) * 2.0


class _VST3:
    @staticmethod
    def get_plugin_names_for_file(_path: str) -> list[str]:
        return ["com.example.gain"]


def _host_with_fake_plugin(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[worker_module._Host, list[_Plugin]]:
    loaded: list[_Plugin] = []

    def load_plugin(_path: str, *, plugin_name: str) -> _Plugin:
        assert plugin_name == "com.example.gain"
        plugin = _Plugin()
        loaded.append(plugin)
        return plugin

    host = worker_module._Host()
    monkeypatch.setattr(host, "_pedalboard", lambda: (object, _VST3, load_plugin))
    return host, loaded


def test_worker_ping_restart_and_clean_shutdown() -> None:
    client = PluginWorkerClient(timeout_seconds=2.0)
    try:
        client.start()
        first = client.status()
        assert first.state == "ready"
        assert first.pid is not None

        restarted = client.restart()
        assert restarted.state == "ready"
        assert restarted.restart_count == 1
        assert restarted.pid != first.pid
    finally:
        client.close()
    assert client.status().state == "stopped"


def test_worker_timeout_terminates_the_subprocess() -> None:
    client = PluginWorkerClient(
        timeout_seconds=0.05,
        discovery_timeout_seconds=0.05,
        command=(sys.executable, "-c", "import time; time.sleep(10)"),
    )
    with pytest.raises(PluginWorkerTimeoutError, match="timed out"):
        client.start()
    assert client.status().state == "failed"


def test_worker_host_probes_controls_state_and_shared_audio(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    host, loaded = _host_with_fake_plugin(monkeypatch)
    binary = tmp_path / "Gain.vst3"
    binary.write_bytes(b"test")

    metadata = host.probe({"path": str(binary)})["plugins"]
    assert metadata == [
        {
            "plugin_identifier": "com.example.gain",
            "name": "Test Gain",
            "manufacturer": "Prism Tests",
            "version": "1.0",
            "category": "Fx",
        }
    ]
    result = host.load(
        {
            "instance_id": "instance",
            "path": str(binary),
            "plugin_identifier": "com.example.gain",
            "state": base64.b64encode(b"restored").decode("ascii"),
            "parameters": {"gain": 0.5},
        }
    )
    plugin = loaded[-1]
    assert plugin.raw_state == b"restored"
    assert result["parameters"][0]["raw_value"] == 0.5

    host.set_parameter(
        {"instance_id": "instance", "parameter_id": "gain", "raw_value": 0.75}
    )
    assert host.parameters({"instance_id": "instance"})["parameters"][0][
        "value"
    ] == "0.75"
    assert base64.b64decode(
        host.get_state({"instance_id": "instance", "max_bytes": 1024})["state"]
    ) == b"restored"
    with pytest.raises(ValueError, match="configured limit"):
        host.get_state({"instance_id": "instance", "max_bytes": 1})

    audio = np.arange(8, dtype=np.float32).reshape(4, 2)
    memory = shared_memory.SharedMemory(create=True, size=audio.nbytes)
    try:
        target = np.ndarray(audio.shape, dtype=np.float32, buffer=memory.buf)
        target[:] = audio
        process_params = {
            "instance_id": "instance",
            "shared_memory": memory.name,
            "frames": 4,
            "channels": 2,
            "sample_rate": 48000,
            "reset": True,
        }
        host.process(process_params)
        assert np.array_equal(target, audio * 2.0)
        assert plugin.process_calls == [(48000, True)]

        host.set_bypass({"instance_id": "instance", "bypassed": True})
        target[:] = audio
        host.process(process_params)
        assert np.array_equal(target, audio)
    finally:
        memory.close()
        memory.unlink()

    host.unload({"instance_id": "instance"})
    with pytest.raises(ValueError, match="not loaded"):
        host.parameters({"instance_id": "instance"})


def test_worker_helpers_reject_malformed_plugin_contracts(tmp_path: Path) -> None:
    binary = tmp_path / "Fallback.vst3"
    binary.write_bytes(b"test")
    assert worker_module._plugin_names(object, str(binary)) == ["Fallback"]

    class EmptyNames:
        @staticmethod
        def get_plugin_names_for_file(_path: str) -> list[str]:
            return []

    assert worker_module._plugin_names(EmptyNames, str(binary)) == ["Fallback"]
    plugin = _Plugin()
    assert worker_module._load(lambda _path: plugin, str(binary), "ignored") is plugin
    with pytest.raises(ValueError, match="between 0 and 1"):
        worker_module._set_parameter(plugin, "gain", 2.0)
    with pytest.raises(ValueError, match="does not exist"):
        worker_module._set_parameter(plugin, "missing", 0.5)
    with pytest.raises(ValueError, match="non-empty"):
        worker_module._string({}, "path")


def test_worker_jsonl_protocol_reports_errors_and_shutdown(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    requests = [
        "not-json",
        WorkerRequest(request_id="ping", method="ping").model_dump_json(),
        WorkerRequest(request_id="unknown", method="unknown").model_dump_json(),
        WorkerRequest(request_id="stop", method="shutdown").model_dump_json(),
    ]
    monkeypatch.setattr(worker_module.sys, "stdin", io.StringIO("\n".join(requests)))

    assert worker_module.main() == 0

    responses = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert responses[0]["request_id"] == "unknown"
    assert responses[0]["error"]["code"] == "worker_error"
    assert responses[1]["result"] == {"ready": True}
    assert responses[2]["error"]["message"] == "Unknown worker method: unknown"
    assert responses[3]["request_id"] == "stop"


def test_worker_jsonl_protocol_contains_unexpected_host_failures(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def crash(_self, _params):
        raise TypeError("bad host")

    monkeypatch.setattr(worker_module._Host, "probe", crash)
    request = WorkerRequest(request_id="probe", method="probe").model_dump_json()
    monkeypatch.setattr(worker_module.sys, "stdin", io.StringIO(request))

    assert worker_module.main() == 0
    response = json.loads(capsys.readouterr().out)
    assert response["error"] == {
        "code": "worker_error",
        "message": "Plugin host failed: bad host",
    }
