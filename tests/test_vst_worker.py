from __future__ import annotations

import json
import sys
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
        return None

    def load_midi(self, path: str) -> bool:
        return True

    def get_latency_samples(self) -> int:
        return 2

    def get_audio(self) -> np.ndarray:
        return np.full((2, self.engine.frames), self.value, dtype=np.float32)


class _FakePlayback:
    def get_name(self) -> str:
        return "prism_input"


class _FakeEngine:
    def __init__(self, sample_rate: int, block_size: int) -> None:
        self.sample_rate = sample_rate
        self.frames = 0
        self.plugin = _FakePlugin(self)

    def set_bpm(self, tempo: float) -> None:
        self.tempo = tempo

    def make_plugin_processor(self, name: str, path: str) -> _FakePlugin:
        return self.plugin

    def make_playback_processor(self, name: str, audio: np.ndarray) -> _FakePlayback:
        return _FakePlayback()

    def load_graph(self, graph: object) -> None:
        self.graph = graph

    def render(self, duration: float) -> bool:
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
            return {}
        frames = int(str(request["frames"]))
        np.save(
            str(request["output_path"]),
            np.full((frames, 2), 0.25, dtype=np.float32),
        )
        return {"frames": frames}

    monkeypatch.setattr(vst_host, "_run_worker", fake_worker)

    assert vst_host.inspect_vst3(project, "test")[0]["name"] == "Depth"
    state = vst_host.edit_vst3(project, "test", "plugin-states/test.state")
    assert state.read_bytes() == b"state"

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
