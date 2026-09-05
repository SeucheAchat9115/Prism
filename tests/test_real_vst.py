from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest

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

    assert output.shape == (int(project.sample_rate), 2)
    assert np.isfinite(output).all()
    assert float(np.max(np.abs(output))) > 1e-7


def test_surge_xt_effect_loads_and_processes_audio(tmp_path: Path) -> None:
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
    plugin = vst3_plugin(
        VST3("surge-fx"),
        name="Surge XT Effects",
        track="Master",
        kind="effect",
    )
    output = process_vst3_effect(project, plugin, source)

    assert output.shape == source.shape
    assert np.isfinite(output).all()
    assert float(np.max(np.abs(output))) > 1e-7
