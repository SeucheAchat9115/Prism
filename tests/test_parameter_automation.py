from __future__ import annotations

from pathlib import Path

import pytest

from prism import VST3, Project, ProjectError, vst_worker
from prism.effects import compile_parameter_envelope, parameter_values
from prism.plugins import CANONICAL_AUTOMATION_VERSION, LEGACY_AUTOMATION_VERSION
from prism.vst import canonical_vst_parameter


def _song(
    script: Path,
    *,
    automation_compatibility: str = CANONICAL_AUTOMATION_VERSION,
) -> Project:
    return Project(
        "Automation boundaries",
        prism_version="test",
        tempo=60,
        sample_rate=8_000,
        normalize=False,
        automation_compatibility=automation_compatibility,
        _script=script,
    )


def test_compiled_envelope_holds_base_before_first_and_last_after_last(
    project_script: Path,
) -> None:
    song = _song(project_script)
    track = song.track("Lead").midi("C4")
    gain = track.effect("gain", gain_db=-12.0)
    song.section("Two bars", bars=2)
    song.automation(
        "Gain movement",
        target=gain,
        parameter="gain_db",
        points=[(0.5, 0.0), (1.5, -6.0)],
        curve="linear",
    )

    envelope = compile_parameter_envelope(song, gain, "gain_db")
    values = parameter_values(song, gain, "gain_db", song.timing.bar_to_frame(2))
    first = song.timing.bar_to_frame(0.5)
    last = song.timing.bar_to_frame(1.5)

    assert envelope.point_frames == (first, last)
    assert not envelope.is_constant
    assert envelope.value_at(first - 1) == -12.0
    assert envelope.value_at(first) == 0.0
    assert envelope.value_at(last + 1) == -6.0
    assert values[first - 1] == -12.0
    assert values[first] == 0.0
    assert values[last + 1] == -6.0
    assert values[song.timing.bar_to_frame(1.0)] == pytest.approx(-3.0)


def test_legacy_first_point_policy_is_explicit_and_serialized(project_script: Path) -> None:
    song = _song(project_script, automation_compatibility=LEGACY_AUTOMATION_VERSION)
    track = song.track("Lead").midi("C4")
    gain = track.effect("gain", gain_db=-12.0)
    song.section("One bar", bars=1)
    song.automation(
        "Late gain",
        target=gain,
        parameter="gain_db",
        points=[(0.5, 0.0), (0.75, -6.0)],
        curve="hold",
    )

    values = parameter_values(song, gain, "gain_db", song.timing.bar_to_frame(1))
    first = song.timing.bar_to_frame(0.5)

    assert song.configuration()["automation_compatibility"] == LEGACY_AUTOMATION_VERSION
    assert values[first - 1] == 0.0
    assert values[first] == 0.0
    assert values[song.timing.bar_to_frame(0.75) + 1] == -6.0


def test_simultaneous_parameter_boundaries_share_exact_frame_timing(
    project_script: Path,
) -> None:
    song = _song(project_script)
    track = song.track("Lead").midi("C4")
    gain = track.effect("gain", gain_db=-12.0)
    filter_effect = track.effect("filter", cutoff_hz=400.0)
    song.section("Two bars", bars=2)
    song.automation(
        "Volume",
        target=gain,
        parameter="gain_db",
        points=[(0.5, -6.0), (1.5, 0.0)],
    )
    song.automation(
        "Filter",
        target=filter_effect,
        parameter="cutoff_hz",
        points=[(0.5, 800.0), (1.5, 1_600.0)],
    )

    boundary = song.timing.bar_to_frame(0.5)
    gain_values = parameter_values(song, gain, "gain_db", boundary + 1)
    filter_values = parameter_values(song, filter_effect, "cutoff_hz", boundary + 1)

    assert gain_values[boundary] == -6.0
    assert filter_values[boundary] == 800.0
    assert gain_values.shape == filter_values.shape


def test_constant_parameter_envelope_stays_sparse(project_script: Path) -> None:
    song = _song(project_script)
    track = song.track("Lead").midi("C4")
    gain = track.effect("gain", gain_db=-12.0)

    envelope = compile_parameter_envelope(song, gain, "gain_db")

    assert envelope.is_constant
    assert envelope.point_frames == ()
    assert envelope.point_values == ()
    assert envelope.base_value == -12.0


def test_vst_name_and_index_selectors_share_inspected_identity() -> None:
    descriptions = [
        {"index": 4, "name": "Renamed Cutoff"},
        {"index": 7, "name": "Depth"},
    ]

    named = canonical_vst_parameter("renamed cutoff", descriptions)
    indexed = canonical_vst_parameter("#4: Old Cutoff", descriptions)

    assert named.parameter_id == indexed.parameter_id == "index:4"
    assert named.index == indexed.index == 4
    assert indexed.selector == "#4: Renamed Cutoff"

    with pytest.raises(ValueError, match="same physical"):
        vst_worker._resolve_parameter_targets(
            ["Renamed Cutoff", "#4: Old Cutoff"], descriptions
        )


def test_vst_selectors_are_rejected_before_render_and_duplicates_are_project_errors(
    tmp_path: Path,
) -> None:
    root = tmp_path / "song"
    root.mkdir()
    script = root / "main.py"
    script.write_text("# test\n", encoding="utf-8")
    plugin_file = root / "Test.vst3"
    plugin_file.write_bytes(b"fake")
    from prism.vst import VSTRegistry

    VSTRegistry(root).initialize()
    VSTRegistry(root).add("synth", plugin_file)
    metadata = (
        {"index": 4, "name": "Renamed Cutoff"},
        {"index": 7, "name": "Depth"},
    )
    song = _song(script)
    track = song.track("Lead").midi(
        "C4",
        instrument=VST3(
            "synth",
            parameters={"Renamed Cutoff": 0.2},
            parameter_metadata=metadata,
        ),
    )
    song.section("One", bars=1, tracks=[track])
    plugin = track.instrument_plugin
    assert plugin is not None
    song.automation(
        "Named lane",
        target=plugin,
        parameter="Renamed Cutoff",
        points=[(0.0, 0.2), (1.0, 0.8)],
    )

    with pytest.raises(ProjectError, match="physical target"):
        song.automation(
            "Indexed duplicate",
            target=plugin,
            parameter="#4: Old Cutoff",
            points=[(0.0, 0.2), (1.0, 0.8)],
        )

    with pytest.raises(ValueError, match="does not exist"):
        vst_worker._resolve_parameter_targets(["Missing"], list(metadata))
    with pytest.raises(ValueError, match="ambiguous"):
        vst_worker._resolve_parameter_targets(
            ["Depth"],
            [{"index": 1, "name": "Depth"}, {"index": 2, "name": "Depth"}],
        )


def test_replaced_vst_instance_recomputes_lane_identity_atomically(tmp_path: Path) -> None:
    root = tmp_path / "song"
    root.mkdir()
    script = root / "main.py"
    script.write_text("# test\n", encoding="utf-8")
    plugin_file = root / "Test.vst3"
    plugin_file.write_bytes(b"fake")
    from prism.vst import VSTRegistry

    VSTRegistry(root).initialize()
    VSTRegistry(root).add("synth", plugin_file)
    metadata = ({"index": 4, "name": "Cutoff"},)
    song = _song(script)
    track = song.track("Lead").midi(
        "C4",
        instrument=VST3("synth", parameters={"Cutoff": 0.2}, parameter_metadata=metadata),
    )
    song.section("One", bars=1, tracks=[track])
    old = track.instrument_plugin
    assert old is not None
    lane = song.automation(
        "Cutoff",
        target=old,
        parameter="#4: Cutoff",
        points=[(0.0, 0.2), (1.0, 0.8)],
    )

    replacement = track.instrument(
        VST3("synth", parameters={"Cutoff": 0.8}, parameter_metadata=metadata)
    )

    assert lane.target is old
    assert song.automation_lanes[0].target is replacement
    assert lane.parameter_identity.instance_id == replacement.stable_instance_id
    assert lane.parameter_identity.parameter_id == "vst3:index:4"
