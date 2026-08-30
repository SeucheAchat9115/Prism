from __future__ import annotations

import json
from pathlib import Path

import pytest

from prism import VST3, Project, ProjectError
from prism import cli as prism_cli
from prism.cli import create_project, main
from prism.vst import VSTRegistry, hash_vst3, platform_key
from prism.vst_host import VSTEditResult, VSTParameterChange


def _project(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "song"
    root.mkdir()
    script = root / "main.py"
    script.write_text("# Prism song\n", encoding="utf-8")
    VSTRegistry(root).initialize()
    plugin = root / "plugins" / "Test Synth.vst3"
    plugin.parent.mkdir()
    plugin.write_bytes(b"fake-vst3")
    return root, plugin


def test_new_projects_include_an_empty_vst_registry(tmp_path: Path) -> None:
    target = create_project(
        "vst-song", _root=tmp_path, _timestamp="20260829-120000"
    )

    assert (target / "plugin-states").is_dir()
    assert json.loads((target / "vst.json").read_text(encoding="utf-8")) == {
        "plugins": {},
        "schema_version": 1,
    }


def test_registry_records_portable_path_and_detects_changes(tmp_path: Path) -> None:
    root, plugin = _project(tmp_path)
    registry = VSTRegistry(root)

    entry = registry.add("My-Synth", plugin)

    assert entry.alias == "my-synth"
    assert entry.platform == platform_key()
    assert entry.path == "plugins/Test Synth.vst3"
    assert entry.sha256 == hash_vst3(plugin)
    assert registry.resolve("MY-SYNTH")[0] == plugin

    plugin.write_bytes(b"changed")
    with pytest.raises(ProjectError, match="has changed"):
        registry.resolve("my-synth")


def test_registry_hashes_a_bundle_deterministically(tmp_path: Path) -> None:
    bundle = tmp_path / "Bundle.vst3"
    (bundle / "Contents" / "x86_64-win").mkdir(parents=True)
    (bundle / "Contents" / "moduleinfo.json").write_text("{}", encoding="utf-8")
    (bundle / "Contents" / "x86_64-win" / "plugin.vst3").write_bytes(b"binary")

    first = hash_vst3(bundle)
    second = hash_vst3(bundle)

    assert first == second
    assert len(first) == 64


def test_registry_requires_replace_and_can_remove(tmp_path: Path) -> None:
    root, plugin = _project(tmp_path)
    registry = VSTRegistry(root)
    registry.add("synth", plugin)

    with pytest.raises(ProjectError, match="--replace"):
        registry.add("synth", plugin)

    registry.add("synth", plugin, replace=True)
    registry.remove("synth")
    assert registry.all_entries() == ()


def test_vst3_declaration_is_normalized_and_safe() -> None:
    plugin = VST3(
        " Serum ",
        state="plugin-states/bass.state",
        parameters={"Filter Cutoff": 0.35},
    )

    assert plugin.alias == "serum"
    assert plugin.parameters["Filter Cutoff"] == 0.35

    with pytest.raises(ProjectError, match="either"):
        VST3("serum", state="a.state", preset="a.vstpreset")
    with pytest.raises(ProjectError, match="between 0 and 1"):
        VST3("serum", parameters={"Cutoff": 1.1})
    with pytest.raises(ProjectError, match="relative path"):
        VST3("serum", state="../outside.state")


def test_external_plugins_share_tracks_effects_and_automation(tmp_path: Path) -> None:
    root, plugin_file = _project(tmp_path)
    VSTRegistry(root).add("serum", plugin_file)
    VSTRegistry(root).add("ott", plugin_file)
    state = root / "plugin-states" / "serum.state"
    state.parent.mkdir()
    state.write_bytes(b"state")
    song = Project("External", prism_version="test", _script=root / "main.py")
    serum = VST3(
        "serum",
        state="plugin-states/serum.state",
        parameters={"Filter Cutoff": 0.3},
    )
    track = song.track("Synth").midi("C3 - G3 -", instrument=serum)
    ott = track.effect(VST3("ott", parameters={"Depth": 0.5}), name="OTT")
    song.section("Loop", bars=1)
    song.automation(
        "OTT depth", target=ott, parameter="Depth", points=[(0.0, 0.2), (1.0, 0.8)]
    )

    summary = song.validate()
    configuration = song.configuration()

    assert summary.tracks == 1
    assert track.instrument_plugin is not None
    assert track.instrument_plugin.vst3 is serum
    assert configuration["schema_version"] == 7
    assert configuration["tracks"][0]["instrument"]["format"] == "vst3"
    assert configuration["tracks"][0]["effects"][0]["external"]["alias"] == "ott"
    assert all("path" not in item for item in configuration["vst3"])


def test_plugin_cli_add_list_and_remove_without_running_main(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root, plugin = _project(tmp_path)
    (root / "main.py").write_text("raise RuntimeError('do not run')\n", encoding="utf-8")

    assert main(["plugins", "add", str(root), "synth", str(plugin)]) == 0
    assert main(["plugins", "list", str(root)]) == 0
    output = capsys.readouterr().out
    assert "Registered synth" in output
    assert "synth [" in output

    assert main(["plugins", "remove", str(root), "synth"]) == 0
    assert VSTRegistry(root).all_entries() == ()


def test_plugin_cli_edit_explains_that_it_is_not_a_live_host(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, plugin = _project(tmp_path)
    VSTRegistry(root).add("synth", plugin)
    saved = root / "plugin-states" / "lead.state"

    def fake_edit(project: Project, alias: str, state: str) -> VSTEditResult:
        assert alias == "synth"
        assert state == "plugin-states/lead.state"
        saved.parent.mkdir()
        saved.write_bytes(b"state")
        return VSTEditResult(
            state_path=saved,
            baseline="plugin_defaults",
            state_changed=True,
            parameter_changes=(
                VSTParameterChange(0, "Cutoff", "Hz", 0.25, 0.75),
            ),
        )

    monkeypatch.setattr(prism_cli, "edit_vst3", fake_edit)

    assert main(
        [
            "plugins",
            "edit",
            str(root),
            "synth",
            "--state",
            "plugin-states/lead.state",
        ]
    ) == 0
    output = capsys.readouterr().out
    assert "no audio preview or musical typing" in output
    assert "Close the plugin window to save" in output
    assert "Compared with plugin defaults" in output
    assert "#0: Cutoff: 0.25 -> 0.75 (normalized, unit: Hz)" in output
    assert "Saved plugin state: plugin-states/lead.state" in output
