from __future__ import annotations

import io
import json
import subprocess
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from prism import VST3, Project, vst_host, vst_worker
from prism.music import ControlPoint, Note
from prism.plugins import vst3_plugin
from prism.vst import VSTRegistry


class _FakePlugin:
    def __init__(self, engine: _FakeEngine) -> None:
        self.engine = engine
        self.value = 0.4
        self.automation: np.ndarray | None = None
        self.editor_opened_while_rendering = False

    def get_parameters_description(self) -> list[dict[str, object]]:
        return [{"index": 0, "name": "Depth", "label": "%", "numSteps": 0}]

    def get_parameter_name(self, index: int) -> str:
        return "Depth"

    def get_parameter(self, index: int) -> float:
        return self.value

    def set_parameter(self, index: int, value: float) -> bool:
        self.value = value
        return True

    def set_automation(self, index: int, data: np.ndarray) -> bool:
        self.automation = data
        return True

    def load_state(self, path: str) -> bool:
        return True

    def save_state(self, path: str) -> bool:
        Path(path).write_bytes(b"state")
        return True

    def load_vst3_preset(self, path: str) -> bool:
        return True

    def open_editor(self) -> None:
        self.editor_opened_while_rendering = self.engine.render_count > 0
        self.value = 0.7
        return None

    def load_midi(self, path: str) -> bool:
        self.engine.midi_load_count += 1
        return True

    def get_latency_samples(self) -> int:
        return 2

    def get_audio(self) -> np.ndarray:
        return np.full((2, self.engine.frames), self.value, dtype=np.float32)


class _FakePlayback:
    def get_name(self) -> str:
        return "prism_input"


class _FakeEngine:
    instances: list[_FakeEngine] = []
    plugin_class = _FakePlugin

    def __init__(self, sample_rate: int, block_size: int) -> None:
        self.__class__.instances.append(self)
        self.sample_rate = sample_rate
        self.block_size = block_size
        self.frames = 0
        self.render_count = 0
        self.midi_load_count = 0
        self.plugin = self.plugin_class(self)

    def set_bpm(self, tempo: float) -> None:
        self.tempo = tempo

    def make_plugin_processor(self, name: str, path: str) -> _FakePlugin:
        return self.plugin

    def make_playback_processor(self, name: str, audio: np.ndarray) -> _FakePlayback:
        return _FakePlayback()

    def load_graph(self, graph: object) -> None:
        self.graph = graph

    def render(self, duration: float) -> bool:
        self.render_count += 1
        self.frames = round(duration * self.sample_rate)
        return True


@pytest.fixture
def fake_daw(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "dawdreamer", SimpleNamespace(RenderEngine=_FakeEngine))


def test_worker_inspects_and_edits_state(tmp_path: Path, fake_daw: None) -> None:
    inspected = vst_worker._execute({"action": "inspect", "plugin_path": "test.vst3"})
    state = tmp_path / "sound.state"
    edited = vst_worker._execute(
        {"action": "edit", "plugin_path": "test.vst3", "state_path": str(state)}
    )

    assert inspected["parameters"][0]["name"] == "Depth"
    assert state.read_bytes() == b"state"
    assert edited["state_path"] == str(state)
    assert edited["baseline"] == "plugin_defaults"
    assert edited["state_changed"] is True
    assert edited["parameter_changes"] == [
        {
            "index": 0,
            "name": "Depth",
            "label": "%",
            "before": 0.4,
            "after": 0.7,
        }
    ]


def test_editor_processing_stops_after_window_closes() -> None:
    engine = _FakeEngine(44_100, 512)

    vst_worker._open_editor_while_processing(engine, engine.plugin)

    assert engine.plugin.editor_opened_while_rendering
    assert engine.render_count >= 1
    assert not any(
        thread.name == "prism-vst3-editor-audio" and thread.is_alive()
        for thread in threading.enumerate()
    )


@pytest.mark.parametrize("action", ("instrument", "effect"))
def test_worker_renders_stereo_and_applies_parameters_and_automation(
    tmp_path: Path, fake_daw: None, action: str
) -> None:
    output = tmp_path / "output.npy"
    automation = tmp_path / "automation.npz"
    np.savez(automation, Depth=np.linspace(0.2, 0.8, 12, dtype=np.float32))
    request: dict[str, object] = {
        "action": action,
        "plugin_path": "test.vst3",
        "output_path": str(output),
        "sample_rate": 10,
        "frames": 10,
        "tempo": 120,
        "parameters": {"depth": 0.6},
        "automation": str(automation),
    }
    if action == "instrument":
        midi = tmp_path / "notes.mid"
        midi.write_bytes(b"midi")
        request["midi_path"] = str(midi)
    else:
        source = tmp_path / "input.npy"
        np.save(source, np.zeros((10, 2), dtype=np.float32))
        request["input_path"] = str(source)

    response = vst_worker._execute(request)
    audio = np.load(output)

    assert response == {"frames": 10, "latency_samples": 2}
    assert audio.shape == (10, 2)
    assert np.allclose(audio, 0.6)


def test_worker_renders_one_complete_instrument_graph_once(
    tmp_path: Path, fake_daw: None
) -> None:
    _FakeEngine.instances.clear()
    output = tmp_path / "output.npy"
    midi = tmp_path / "complete-track.mid"
    midi.write_bytes(b"leading silence, sections, overlap, and tail")

    response = vst_worker._execute(
        {
            "action": "instrument",
            "plugin_path": "test.vst3",
            "midi_path": str(midi),
            "output_path": str(output),
            "sample_rate": 10,
            "frames": 100,
            "tempo": 120,
        }
    )

    assert response == {"frames": 100, "latency_samples": 2}
    assert len(_FakeEngine.instances) == 1
    engine = _FakeEngine.instances[0]
    assert engine.midi_load_count == 1
    assert engine.render_count == 1


def test_worker_uses_validated_block_size_and_reports_capabilities(
    tmp_path: Path, fake_daw: None
) -> None:
    _FakeEngine.instances.clear()
    output = tmp_path / "output.npy"
    midi = tmp_path / "notes.mid"
    midi.write_bytes(b"midi")

    response = vst_worker._execute(
        {
            "action": "instrument",
            "plugin_path": "test.vst3",
            "midi_path": str(midi),
            "output_path": str(output),
            "sample_rate": 10,
            "frames": 10,
            "backend": {"render_block_size": 256},
        }
    )

    assert _FakeEngine.instances[0].block_size == 256
    backend = response["backend"]
    assert isinstance(backend, dict)
    assert backend["render_block_size"] == 256
    assert backend["backend_capabilities"] == {
        "render_engine": True,
        "plugin_processor": True,
        "playback_processor": True,
    }
    assert backend["plugin_capabilities"]["latency_query"] is True  # type: ignore[index]


class _ChangingLatencyPlugin(_FakePlugin):
    def __init__(self, engine: _FakeEngine) -> None:
        super().__init__(engine)
        self.latency_calls = 0

    def get_latency_samples(self) -> int:
        self.latency_calls += 1
        return 2 if self.latency_calls == 1 else 4


class _ChangingLatencyEngine(_FakeEngine):
    plugin_class = _ChangingLatencyPlugin


def test_worker_reconciles_latency_after_graph_preparation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(
        sys.modules, "dawdreamer", SimpleNamespace(RenderEngine=_ChangingLatencyEngine)
    )
    output = tmp_path / "output.npy"
    source = tmp_path / "input.npy"
    np.save(source, np.zeros((10, 2), dtype=np.float32))

    response = vst_worker._execute(
        {
            "action": "effect",
            "plugin_path": "test.vst3",
            "input_path": str(source),
            "output_path": str(output),
            "sample_rate": 10,
            "frames": 10,
            "backend": {"render_block_size": 128},
        }
    )

    assert response["latency_samples_before_graph"] == 2
    assert response["latency_samples"] == 4
    assert response["latency_reconciled"] is True
    assert len(_ChangingLatencyEngine.instances) >= 1
    assert _ChangingLatencyEngine.instances[-1].render_count == 1


class _ImpulsePlayback:
    def __init__(self, audio: np.ndarray) -> None:
        self.audio = audio

    def get_name(self) -> str:
        return "prism_input"


class _LatencyImpulsePlugin(_FakePlugin):
    def get_audio(self) -> np.ndarray:
        playback = self.engine.playback
        latency = self.get_latency_samples()
        return np.concatenate(
            (np.zeros((2, latency), dtype=np.float32), playback.audio), axis=1
        )


class _LatencyImpulseEngine(_FakeEngine):
    plugin_class = _LatencyImpulsePlugin

    def make_playback_processor(self, name: str, audio: np.ndarray) -> _ImpulsePlayback:
        self.playback = _ImpulsePlayback(audio)
        return self.playback


def test_worker_compensates_one_known_effect_latency_without_moving_impulse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(
        sys.modules, "dawdreamer", SimpleNamespace(RenderEngine=_LatencyImpulseEngine)
    )
    output = tmp_path / "output.npy"
    source = np.zeros((10, 2), dtype=np.float32)
    source[0] = 1.0
    input_path = tmp_path / "input.npy"
    np.save(input_path, source)

    vst_worker._execute(
        {
            "action": "effect",
            "plugin_path": "test.vst3",
            "input_path": str(input_path),
            "output_path": str(output),
            "sample_rate": 10,
            "frames": 10,
            "backend": {"render_block_size": 128},
        }
    )

    rendered = np.load(output)
    assert np.argmax(np.abs(rendered[:, 0])) == 0
    assert rendered[0, 0] == pytest.approx(1.0)
    assert np.count_nonzero(rendered) == 2


def test_worker_precedence_is_state_then_parameters_then_automation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    order: list[str] = []
    state = tmp_path / "saved.state"
    preset = tmp_path / "ignored.vstpreset"
    state.write_bytes(b"state")
    preset.write_bytes(b"preset")
    automation = tmp_path / "automation.npz"
    np.savez(automation, Depth=np.linspace(0.2, 0.8, 10, dtype=np.float32))

    class RecordingPlugin(_FakePlugin):
        def load_state(self, path: str) -> bool:
            order.append("state")
            return True

        def load_vst3_preset(self, path: str) -> bool:
            order.append("preset")
            return True

        def set_parameter(self, index: int, value: float) -> bool:
            order.append("parameter")
            return super().set_parameter(index, value)

        def set_automation(self, index: int, data: np.ndarray) -> bool:
            order.append("automation")
            return super().set_automation(index, data)

    class RecordingEngine(_FakeEngine):
        plugin_class = RecordingPlugin

    monkeypatch.setitem(sys.modules, "dawdreamer", SimpleNamespace(RenderEngine=RecordingEngine))
    output = tmp_path / "output.npy"
    midi = tmp_path / "notes.mid"
    midi.write_bytes(b"midi")
    vst_worker._execute(
        {
            "action": "instrument",
            "plugin_path": "test.vst3",
            "midi_path": str(midi),
            "output_path": str(output),
            "sample_rate": 10,
            "frames": 10,
            "state_path": str(state),
            "preset_path": str(preset),
            "parameters": {"Depth": 0.9},
            "automation": str(automation),
        }
    )

    assert order == ["state", "parameter", "automation"]
    assert "preset" not in order


def test_failed_state_save_preserves_previous_state_and_cleans_temporary_file(
    tmp_path: Path, fake_daw: None
) -> None:
    state = tmp_path / "lead.state"
    state.write_bytes(b"previous")

    class FailingPlugin(_FakePlugin):
        def save_state(self, path: str) -> bool:
            Path(path).write_bytes(b"partial")
            return False

    plugin = FailingPlugin(_FakeEngine(44_100, 512))
    with pytest.raises(RuntimeError, match="Could not save the VST3 state"):
        vst_worker._save_state_atomically(plugin, state)

    assert state.read_bytes() == b"previous"
    assert list(tmp_path.glob(f".{state.name}.*.tmp")) == []


@pytest.mark.parametrize("bad_audio", ["short", "nonfinite"])
def test_worker_rejects_short_or_nonfinite_plugin_audio(
    tmp_path: Path, fake_daw: None, monkeypatch: pytest.MonkeyPatch, bad_audio: str
) -> None:
    output = tmp_path / "output.npy"
    midi = tmp_path / "notes.mid"
    midi.write_bytes(b"midi")

    def bad_output(plugin: _FakePlugin) -> np.ndarray:
        if bad_audio == "short":
            return np.zeros((2, plugin.engine.frames - 1), dtype=np.float32)
        return np.full((2, plugin.engine.frames), np.nan, dtype=np.float32)

    monkeypatch.setattr(_FakePlugin, "get_audio", bad_output)
    with pytest.raises(RuntimeError, match="(expected at least|non-finite)"):
        vst_worker._execute(
            {
                "action": "instrument",
                "plugin_path": "test.vst3",
                "midi_path": str(midi),
                "output_path": str(output),
                "sample_rate": 10,
                "frames": 10,
            }
        )


class _HangingProcess:
    pid = 12345

    def __init__(self) -> None:
        self.stdout = io.BytesIO(b"o" * 100_000)
        self.stderr = io.BytesIO(b"e" * 100_000)
        self.terminated = False

    def poll(self) -> int | None:
        return -15 if self.terminated else None

    def wait(self, timeout: float | None = None) -> int:
        if not self.terminated:
            raise subprocess.TimeoutExpired("worker", timeout)
        return -15

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.terminated = True


def test_host_cancellation_terminates_worker_and_bounds_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process = _HangingProcess()
    cancelled = threading.Event()
    cancelled.set()
    terminated: list[bool] = []

    monkeypatch.setattr(vst_host, "_start_worker", lambda *_args: process)

    def terminate(worker: object, *, force: bool = False) -> None:
        assert worker is process
        terminated.append(force)
        process.terminate()

    monkeypatch.setattr(vst_host, "_terminate_process_tree", terminate)
    with pytest.raises(vst_host.VSTWorkerError) as raised:
        vst_host._run_worker(
            {
                "action": "instrument",
                "plugin_alias": "hanging",
                "track": "Lead",
                "backend": {"diagnostic_limit": 256},
            },
            cancel_event=cancelled,
        )

    diagnostics = raised.value.diagnostics
    assert diagnostics.cancelled
    assert not diagnostics.timed_out
    assert diagnostics.operation == "instrument"
    assert diagnostics.plugin_alias == "hanging"
    assert diagnostics.track == "Lead"
    assert len(diagnostics.stdout) <= 256 + 40
    assert len(diagnostics.stderr) <= 256 + 40
    assert process.terminated
    assert terminated == [False]


def test_worker_main_reports_plugin_errors(
    tmp_path: Path, fake_daw: None, capsys: pytest.CaptureFixture[str]
) -> None:
    request = tmp_path / "request.json"
    response = tmp_path / "response.json"
    request.write_text(json.dumps({"action": "wrong", "plugin_path": "x"}))

    assert vst_worker.main([str(request), str(response)]) == 1
    assert "Unknown VST3 worker action" in capsys.readouterr().err
    assert vst_worker.main([]) == 2


def _external_project(tmp_path: Path) -> tuple[Project, object]:
    root = tmp_path / "song"
    root.mkdir()
    script = root / "main.py"
    script.write_text("# song\n", encoding="utf-8")
    binary = root / "test.vst3"
    binary.write_bytes(b"plugin")
    registry = VSTRegistry(root)
    registry.initialize()
    registry.add("test", binary)
    project = Project("Host", prism_version="test", _script=script)
    plugin = vst3_plugin(
        VST3("test", parameters={"Depth": 0.4}),
        name="Test",
        track="Master",
        kind="effect",
    )
    return project, plugin


def test_host_inspection_edit_and_audio_round_trip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, plugin = _external_project(tmp_path)

    def fake_worker(request: dict[str, object]) -> dict[str, object]:
        action = request["action"]
        if action == "inspect":
            return {"parameters": [{"index": 0, "name": "Depth", "value": 0.4}]}
        if action == "edit":
            Path(str(request["state_path"])).write_bytes(b"state")
            return {
                "baseline": "plugin_defaults",
                "state_changed": True,
                "parameter_changes": [
                    {
                        "index": 0,
                        "name": "Depth",
                        "label": "%",
                        "before": 0.4,
                        "after": 0.6,
                    }
                ],
            }
        frames = int(str(request["frames"]))
        np.save(
            str(request["output_path"]),
            np.full((frames, 2), 0.25, dtype=np.float32),
        )
        return {"frames": frames}

    monkeypatch.setattr(vst_host, "_run_worker", fake_worker)

    assert vst_host.inspect_vst3(project, "test")[0]["name"] == "Depth"
    edited = vst_host.edit_vst3(project, "test", "plugin-states/test.state")
    assert edited.state_path.read_bytes() == b"state"
    assert edited.parameter_changes[0].name == "Depth"

    effect = vst_host.process_vst3_effect(
        project, plugin, np.zeros((20, 2), dtype=np.float64)
    )
    instrument = vst3_plugin(
        VST3("test"), name="Synth", track="Lead", kind="instrument"
    )
    rendered = vst_host.render_vst3_instrument(
        project,
        instrument,
        [Note("C4", 0.0, 1.0)],
        [ControlPoint(0.0, 0.0)],
        [ControlPoint(0.0, 0.5)],
        20,
    )

    assert np.allclose(effect, 0.25)
    assert np.allclose(rendered, 0.25)


def test_parameter_selectors_and_midi_payload_are_valid() -> None:
    descriptions = [
        {"index": 4, "name": "Depth"},
        {"index": 7, "name": "Depth"},
    ]
    assert vst_worker._parameter_index("#4: Depth", descriptions) == 4
    with pytest.raises(ValueError, match="ambiguous"):
        vst_worker._parameter_index("depth", descriptions)
    with pytest.raises(ValueError, match="does not exist"):
        vst_worker._parameter_index("Missing", descriptions)

    payload = vst_host._midi_file(
        120,
        [Note("C4", 0.0, 1.0, 100)],
        [ControlPoint(0.0, -2.0), ControlPoint(1.0, 2.0)],
        [ControlPoint(0.5, 1.0)],
    )
    assert payload.startswith(b"MThd")
    assert b"MTrk" in payload
