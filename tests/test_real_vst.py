from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from prism import VST3, Project
from prism.music import Note
from prism.plugins import vst3_plugin
from prism.vst import VSTRegistry
from prism.vst_host import (
    inspect_vst3,
    process_vst3_effect,
    render_vst3_instrument,
)


def _required_path(variable: str) -> Path:
    value = os.environ.get(variable)
    if not value:
        pytest.skip(f"{variable} is not configured")
    path = Path(value)
    if not path.exists():
        pytest.fail(f"{variable} points to a missing path: {path}")
    return path


def _diagnostics_directory(tmp_path: Path) -> Path:
    configured = os.environ.get("PRISM_VST_DIAGNOSTICS_DIR")
    directory = Path(configured) if configured else tmp_path / "vst-diagnostics"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _audio_metrics(samples: np.ndarray, sample_rate: int) -> dict[str, object]:
    magnitude = np.max(np.abs(samples), axis=1)
    active = np.flatnonzero(magnitude > 1e-7)
    rms = float(np.sqrt(np.mean(np.square(samples)))) if samples.size else 0.0
    tail_start = min(samples.shape[0], round(0.45 * sample_rate))
    tail = samples[tail_start:]
    tail_rms = float(np.sqrt(np.mean(np.square(tail)))) if tail.size else 0.0
    return {
        "frames": int(samples.shape[0]),
        "channels": int(samples.shape[1]),
        "sample_rate": sample_rate,
        "peak": float(np.max(magnitude)) if magnitude.size else 0.0,
        "rms": rms,
        "onset_frame": None if active.size == 0 else int(active[0]),
        "last_active_frame": None if active.size == 0 else int(active[-1]),
        "audible_duration_seconds": (
            0.0 if active.size == 0 else float((active[-1] + 1) / sample_rate)
        ),
        "tail_rms": tail_rms,
    }


def _save_audio_diagnostics(
    directory: Path,
    name: str,
    samples: np.ndarray,
    sample_rate: int,
    **metadata: object,
) -> None:
    """Keep a small WAV and JSON bundle when a real-plugin assertion fails."""

    sf.write(
        directory / f"{name}.wav",
        np.asarray(samples, dtype=np.float32),
        sample_rate,
        subtype="FLOAT",
    )
    payload = {"metrics": _audio_metrics(samples, sample_rate), **metadata}
    (directory / f"{name}.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )


def _save_failure_diagnostics(
    directory: Path, name: str, error: BaseException
) -> None:
    (directory / f"{name}.json").write_text(
        json.dumps({"error": type(error).__name__, "message": str(error)}, indent=2),
        encoding="utf-8",
    )


def _project(tmp_path: Path, instrument: Path, effect: Path) -> Project:
    root = tmp_path / "real-vst"
    root.mkdir()
    script = root / "main.py"
    script.write_text("# real VST integration fixture\n", encoding="utf-8")
    registry = VSTRegistry(root)
    registry.initialize()
    registry.add("surge", instrument)
    registry.add("surge-fx", effect)
    return Project("Surge XT CI", prism_version="ci", _script=script)


def test_surge_xt_instrument_loads_inspects_and_renders(tmp_path: Path) -> None:
    diagnostics = _diagnostics_directory(tmp_path)
    try:
        instrument = _required_path("PRISM_SURGE_INSTRUMENT_VST3")
        effect = _required_path("PRISM_SURGE_EFFECT_VST3")
        project = _project(tmp_path, instrument, effect)

        parameters = inspect_vst3(project, "surge")
        assert parameters, "Surge XT did not expose any VST3 parameters."
        selected = next(
            (
                item
                for item in parameters
                if str(item["name"]).casefold() == "global volume"
            ),
            parameters[0],
        )
        index = selected["index"]
        name = selected["name"]
        assert isinstance(index, int)
        assert isinstance(name, str)
        plugin = vst3_plugin(
            VST3("surge", parameters={f"#{index}: {name}": 0.75}),
            name="Surge XT",
            track="Lead",
            kind="instrument",
        )
        output = render_vst3_instrument(
            project,
            plugin,
            (Note("C4", 0.0, 0.5),),
            (),
            (),
            int(project.sample_rate),
        )
        _save_audio_diagnostics(
            diagnostics,
            "surge-instrument",
            output,
            int(project.sample_rate),
            plugin="Surge XT",
            platform=os.name,
        )

        metrics = _audio_metrics(output, int(project.sample_rate))
        assert output.shape == (int(project.sample_rate), 2)
        assert np.isfinite(output).all()
        assert float(metrics["peak"]) > 1e-7
        assert metrics["onset_frame"] is not None
        assert int(metrics["onset_frame"]) < int(project.sample_rate * 0.1)
        assert float(metrics["rms"]) > 1e-4
        assert float(metrics["audible_duration_seconds"]) > 0.25
    except BaseException as error:
        _save_failure_diagnostics(diagnostics, "surge-instrument-failure", error)
        raise


def test_surge_xt_effect_loads_and_processes_audio(tmp_path: Path) -> None:
    diagnostics = _diagnostics_directory(tmp_path)
    try:
        instrument = _required_path("PRISM_SURGE_INSTRUMENT_VST3")
        effect = _required_path("PRISM_SURGE_EFFECT_VST3")
        project = _project(tmp_path, instrument, effect)
        frames = int(project.sample_rate) // 2
        timeline = np.arange(frames, dtype=np.float64) / project.sample_rate
        source = np.column_stack(
            (
                0.25 * np.sin(2 * np.pi * 220 * timeline),
                0.25 * np.sin(2 * np.pi * 330 * timeline),
            )
        )
        parameters = inspect_vst3(project, "surge-fx")
        selected = next(
            (
                item
                for item in parameters
                if any(
                    token in str(item["name"]).casefold()
                    for token in ("mix", "wet", "depth", "drive", "feedback")
                )
            ),
            None,
        )
        assert selected is not None, "Surge XT Effects exposed no measurable control."
        index = selected["index"]
        name = selected["name"]
        assert isinstance(index, int)
        assert isinstance(name, str)
        plugin = vst3_plugin(
            VST3("surge-fx", parameters={f"#{index}: {name}": 0.8}),
            name="Surge XT Effects",
            track="Master",
            kind="effect",
        )
        output = process_vst3_effect(project, plugin, source)
        _save_audio_diagnostics(
            diagnostics,
            "surge-effect",
            output,
            int(project.sample_rate),
            plugin="Surge XT Effects",
            configured_parameter=name,
            configured_value=0.8,
            input_peak=float(np.max(np.abs(source))),
            difference_peak=float(np.max(np.abs(output - source))),
        )

        assert output.shape == source.shape
        assert np.isfinite(output).all()
        assert float(np.max(np.abs(output))) > 1e-7
        assert float(np.max(np.abs(output - source))) > 1e-5
    except BaseException as error:
        _save_failure_diagnostics(diagnostics, "surge-effect-failure", error)
        raise


def test_surge_xt_project_render_writes_a_non_silent_wav(tmp_path: Path) -> None:
    diagnostics = _diagnostics_directory(tmp_path)
    try:
        instrument = _required_path("PRISM_SURGE_INSTRUMENT_VST3")
        effect = _required_path("PRISM_SURGE_EFFECT_VST3")
        project = _project(tmp_path, instrument, effect)
        track = project.track("Lead").midi(
            (Note("C4", 0.0, 0.5),),
            instrument=VST3("surge"),
            bars=1,
            repeat=False,
        )
        project.section("Only", bars=1, tracks=[track])

        result = project.render("renders/surge-xt.wav", bit_depth=32)
        samples, sample_rate = sf.read(result.path, dtype="float32", always_2d=True)
        _save_audio_diagnostics(
            diagnostics,
            "surge-project",
            samples,
            sample_rate,
            plugin="Surge XT",
            render_sha256=result.sha256,
        )
        peak = float(np.max(np.abs(samples)))

        assert result.path.is_file()
        assert sample_rate == project.sample_rate
        assert samples.shape == (project.frames_per_bar, 2)
        assert np.isfinite(samples).all()
        assert peak > 1e-4, f"Rendered WAV is silent or near-silent (peak={peak:g})."
    except BaseException as error:
        _save_failure_diagnostics(diagnostics, "surge-project-failure", error)
        raise


def _fixture_project(tmp_path: Path) -> tuple[Project, Path, Path]:
    instrument = _required_path("PRISM_FIXTURE_INSTRUMENT_VST3")
    effect = _required_path("PRISM_FIXTURE_EFFECT_VST3")
    root = tmp_path / "fixture-vst"
    root.mkdir()
    script = root / "main.py"
    script.write_text("# pinned VST3 qualification fixture\n", encoding="utf-8")
    registry = VSTRegistry(root)
    registry.initialize()
    registry.add("fixture-instrument", instrument)
    registry.add("fixture-effect", effect)
    return Project("Pinned VST3 fixtures", prism_version="ci", _script=script), instrument, effect


def test_pinned_fixture_instrument_has_onset_and_midi_response(tmp_path: Path) -> None:
    diagnostics = _diagnostics_directory(tmp_path)
    try:
        project, _instrument, effect = _fixture_project(tmp_path)
        parameters = inspect_vst3(project, "fixture-instrument")
        assert parameters, "The pinned fixture instrument exposed no parameters."
        plugin = vst3_plugin(
            VST3("fixture-instrument"),
            name="Pinned fixture instrument",
            track="Fixture",
            kind="instrument",
        )
        output = render_vst3_instrument(
            project, plugin, (Note("C4", 0.0, 0.25),), (), (), int(project.sample_rate)
        )
        _save_audio_diagnostics(
            diagnostics,
            "fixture-instrument",
            output,
            int(project.sample_rate),
            plugin_path=str(_instrument),
            effect_path=str(effect),
        )
        metrics = _audio_metrics(output, int(project.sample_rate))
        assert metrics["onset_frame"] is not None
        assert float(metrics["rms"]) > 1e-5
        assert float(metrics["audible_duration_seconds"]) >= 0.1
    except BaseException as error:
        _save_failure_diagnostics(diagnostics, "fixture-instrument-failure", error)
        raise


def test_pinned_fixture_effect_has_configured_impulse_delay(tmp_path: Path) -> None:
    diagnostics = _diagnostics_directory(tmp_path)
    try:
        project, instrument, _effect = _fixture_project(tmp_path)
        parameters = inspect_vst3(project, "fixture-effect")
        delay = next(
            (item for item in parameters if "delay" in str(item["name"]).casefold()),
            None,
        )
        assert delay is not None, "The pinned fixture effect exposed no delay control."
        index = delay["index"]
        name = delay["name"]
        assert isinstance(index, int)
        assert isinstance(name, str)
        frames = int(project.sample_rate) // 4
        source = np.zeros((frames, 2), dtype=np.float64)
        source[0] = 1.0
        plugin = vst3_plugin(
            VST3("fixture-effect", parameters={f"#{index}: {name}": 0.01}),
            name="Pinned fixture effect",
            track="Fixture",
            kind="effect",
        )
        output = process_vst3_effect(project, plugin, source)
        _save_audio_diagnostics(
            diagnostics,
            "fixture-effect",
            output,
            int(project.sample_rate),
            plugin_path=str(_effect),
            instrument_path=str(instrument),
            configured_parameter=name,
        )
        assert output.shape == source.shape
        assert np.isfinite(output).all()
        assert float(np.max(np.abs(output))) > 1e-5
        assert int(np.argmax(np.abs(output[:, 0]))) > 0
    except BaseException as error:
        _save_failure_diagnostics(diagnostics, "fixture-effect-failure", error)
        raise


def _qualification_test(function):
    from functools import wraps

    @wraps(function)
    def checked(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except Exception as error:
            directory = _diagnostics_directory(kwargs["tmp_path"])
            _save_failure_diagnostics(directory, function.__name__ + "-failure", error)
            raise
    return checked


def _latency_project(tmp_path, *, mono=False):
    path = _required_path("PRISM_FIXTURE_MONO_VST3" if mono else "PRISM_FIXTURE_LATENCY_VST3")
    root = tmp_path / "latency-project"
    root.mkdir(exist_ok=True)
    (root / "main.py").write_text("# controlled latency qualification\n", encoding="utf-8")
    registry = VSTRegistry(root)
    registry.initialize()
    registry.add("latency", path)
    return Project("Latency", prism_version="test", project_root=root, sample_rate=8000), path


def _gain_plugin(**kwargs):
    return vst3_plugin(VST3("latency", **kwargs), name="Gain", track="Test", kind="effect")


@_qualification_test
def test_real_reported_latency_serial_and_parallel_alignment(tmp_path):
    project, path = _latency_project(tmp_path)
    import dawdreamer as daw
    source = np.zeros((4096, 2), dtype=np.float32)
    source[173] = [0.5, -0.25]
    engine = daw.RenderEngine(8000, 128)
    plugin = engine.make_plugin_processor("gain", str(path))
    playback = engine.make_playback_processor("input", np.pad(source.T, ((0, 0), (0, 64))))
    engine.load_graph([(playback, []), (plugin, ["input"])])
    assert plugin.get_latency_samples() == 64
    engine.render((len(source) + 64) / 8000)
    raw = np.asarray(plugin.get_audio()).T
    _save_audio_diagnostics(_diagnostics_directory(tmp_path), "raw-latency", raw, 8000)
    assert np.argmax(np.abs(raw[:, 0])) == 173 + 64
    first = process_vst3_effect(project, _gain_plugin(parameters={"Gain": 0.5}), source)
    second = process_vst3_effect(project, _gain_plugin(parameters={"Gain": 0.5}), first)
    _save_audio_diagnostics(_diagnostics_directory(tmp_path), "serial-latency", second, 8000)
    np.testing.assert_allclose(first, source * 0.5, atol=1e-7)
    np.testing.assert_allclose(second, source * 0.25, atol=1e-7)
    np.testing.assert_allclose(source + second, source * 1.25, atol=1e-7)


@pytest.mark.parametrize("asset", ["state", "preset"])
@_qualification_test
def test_real_state_preset_overrides_and_late_automation(tmp_path, asset):
    import struct

    from prism.vst_worker import _save_state_atomically

    project, path = _latency_project(tmp_path)
    import dawdreamer as daw

    relative = "patch.state" if asset == "state" else "patch.vstpreset"
    destination = project.root / relative
    if asset == "state":
        engine = daw.RenderEngine(8000, 128)
        raw = engine.make_plugin_processor("gain", str(path))
        raw.set_parameter(0, 0.25)
        playback = engine.make_playback_processor("input", np.zeros((2, 1024), np.float32))
        engine.load_graph([(playback, []), (raw, ["input"])])
        engine.render(1024 / 8000)
        _save_state_atomically(raw, destination)
    else:
        # Standard VST3 preset: header, processor component state, chunk list.
        class_id = b"42ABCC11221344556677889910111213"
        destination.write_bytes(
            b"VST3" + struct.pack("<i", 1) + class_id + struct.pack("<q", 56)
            + struct.pack("<d", 0.25)
            + b"List" + struct.pack("<i", 1) + b"Comp" + struct.pack("<qq", 48, 8)
        )
    source = np.full((8000, 2), 0.25, np.float32)
    settings = {asset: relative}
    saved = process_vst3_effect(project, _gain_plugin(**settings), source)
    np.testing.assert_allclose(saved, source * 0.25, atol=1e-7)
    plugin = project.master_effect(VST3("latency", **settings, parameters={"Gain": 0.75}))
    overridden = process_vst3_effect(project, plugin, source)
    np.testing.assert_allclose(overridden, source * 0.75, atol=1e-7)
    project.automation("Late gain", target=plugin, parameter="Gain", points=[(0.25, 0.5)])
    automated = process_vst3_effect(project, plugin, source)
    first = project.timing.bar_to_frame(0.25)
    # DawDreamer samples automation at each block start. Verify the exact
    # block-quantized boundary, including the non-aligned authored frame.
    block = project.vst_backend.render_block_size
    first = ((first + block - 1) // block) * block
    _save_audio_diagnostics(
        _diagnostics_directory(tmp_path), f"{asset}-automation", automated, 8000
    )
    np.testing.assert_allclose(automated[:first], source[:first] * 0.75, atol=1e-7)
    np.testing.assert_allclose(automated[first:], source[first:] * 0.5, atol=1e-7)
    # Also hold the loaded state value when there is no explicit parameter override.
    project.automation_lanes.clear()
    loaded = project.master_effect(VST3("latency", **settings))
    project.automation("Late loaded gain", target=loaded, parameter="Gain", points=[(0.25, 0.5)])
    automated = process_vst3_effect(project, loaded, source)
    np.testing.assert_allclose(automated[:first], source[:first] * 0.25, atol=1e-7)


@_qualification_test
def test_real_mono_plugin_output_is_aligned_and_energy_preserving(tmp_path):
    project, _ = _latency_project(tmp_path, mono=True)
    source = np.zeros((4096, 2), np.float32)
    source[123] = [0.75, 0.25]
    output = process_vst3_effect(project, _gain_plugin(parameters={"Gain": 1.0}), source)
    expected = np.repeat(np.mean(source, axis=1, keepdims=True), 2, axis=1) / np.sqrt(2)
    _save_audio_diagnostics(_diagnostics_directory(tmp_path), "mono-latency", output, 8000)
    np.testing.assert_allclose(output, expected, atol=1e-7)
