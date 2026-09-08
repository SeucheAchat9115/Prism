from __future__ import annotations

import json
from pathlib import Path

import pytest

from prism import (
    VST3,
    AgentError,
    AgentLimits,
    AgentOperationRequest,
    Project,
    ProjectError,
    agent_capabilities,
    agent_operation,
    build_agent_operation,
    inspect_agent_context,
    project_revision_id,
)
from prism.cli import main
from prism.fingerprint import migrate_project_configuration
from prism.vst import VSTRegistry


def _duplicate_name_project(script: Path) -> Project:
    song = Project(
        "Agent Fixture",
        prism_version="test",
        project_id="fixture-song",
        key="C",
        scale="minor",
        chords=("Cm", "Ab"),
        _script=script,
    )
    bass = song.track(
        "Lead",
        track_id="track-bass",
        role="bass",
        allow_duplicate_name=True,
    )
    bass.midi("C2 Eb2 G2", bars=1, clip_definition_id="clip-bass")
    lead = song.track(
        "Lead",
        track_id="track-lead",
        role="lead",
        allow_duplicate_name=True,
    )
    lead.midi("G4 Bb4", bars=1, clip_definition_id="clip-lead")
    song.section("Verse", section_id="section-verse", bars=2, tracks=[bass, lead])
    return song


def test_agent_context_has_stable_ids_musical_provenance_and_bounds(
    project_script: Path,
) -> None:
    song = _duplicate_name_project(project_script)

    first = inspect_agent_context(
        song,
        limits={"max_notes": 1, "max_clip_instances": 1},
    )
    tracks = first["arrangement"]["tracks"]  # type: ignore[index]
    assert [track["id"] for track in tracks] == ["track-bass", "track-lead"]
    assert first["project_id"] == "fixture-song"
    assert "notes" in first["bounds"]["truncated"]  # type: ignore[index]
    assert "clip_instances" in first["bounds"]["truncated"]  # type: ignore[index]
    assert first["musical_context"]["authored"]["key"] == {  # type: ignore[index]
        "value": "C",
        "source": "authored",
    }
    inferred = first["musical_context"]["inferred"]["harmony"]  # type: ignore[index]
    assert inferred["source"] == "inferred"
    assert 0.0 <= inferred["uncertainty"] <= 1.0
    assert first["arrangement"]["tracks"][0]["register"]["source"] == "inferred"  # type: ignore[index]

    original_ids = {
        "track": tracks[0]["id"],
        "clip": first["arrangement"]["clip_definitions"][0]["id"],  # type: ignore[index]
        "section": first["arrangement"]["sections"][0]["id"],  # type: ignore[index]
        "plugin": first["plugins"]["instances"][0]["id"],  # type: ignore[index]
    }
    configuration = song.configuration()
    assert configuration["identity_schema_version"] == 1
    assert configuration["tracks"][0]["id"] == "track-bass"  # type: ignore[index]
    assert configuration["tracks"][0]["clips"][0]["id"] == "clip-bass"  # type: ignore[index]
    assert configuration["tracks"][0]["instrument"]["plugin_id"] == original_ids["plugin"]  # type: ignore[index]
    song.name = "Renamed Agent Fixture"
    song.tracks[0].name = "Bass (renamed)"
    second = inspect_agent_context(song)
    assert second["project_id"] == first["project_id"]
    assert second["arrangement"]["tracks"][0]["id"] == original_ids["track"]  # type: ignore[index]
    assert second["arrangement"]["clip_definitions"][0]["id"] == original_ids["clip"]  # type: ignore[index]
    assert second["arrangement"]["sections"][0]["id"] == original_ids["section"]  # type: ignore[index]
    assert second["plugins"]["instances"][0]["id"] == original_ids["plugin"]  # type: ignore[index]


def test_agent_selection_is_unambiguous_and_reports_revision_errors(
    project_script: Path,
) -> None:
    song = _duplicate_name_project(project_script)
    ambiguous = agent_operation(
        song,
        {"operation": "select", "selection": {"entity": "track", "name": "Lead"}},
    )
    assert ambiguous["status"] == "error"
    assert ambiguous["error"]["code"] == "ambiguous_name"  # type: ignore[index]

    selected = agent_operation(
        song,
        {
            "operation": "select",
            "selection": {
                "entity": "track",
                "id": "track-bass",
                "section": "section-verse",
                "quarter_note_range": [0, 4],
            },
        },
    )
    assert selected["status"] == "ok"
    assert selected["selected_ranges"] == [{"start_beat": 0.0, "end_beat": 4.0}]
    assert selected["result"]["items"][0]["id"] == "track-bass"  # type: ignore[index]

    unknown = agent_operation(
        song,
        {"operation": "select", "selection": {"entity": "track", "id": "gone"}},
    )
    assert unknown["error"]["code"] == "unknown_id"  # type: ignore[index]

    stale = agent_operation(
        song,
        {
            "operation": "select",
            "revision_id": "sha256:old",
            "selection": {"entity": "track", "id": "track-bass"},
        },
    )
    assert stale["error"]["code"] == "stale_revision"  # type: ignore[index]

    future = agent_operation(song, {"schema_version": 99, "operation": "inspect"})
    assert future["error"]["code"] == "unsupported_schema_version"  # type: ignore[index]


def test_missing_optional_vst_is_inspectable_without_host_or_network(
    project_script: Path,
) -> None:
    song = Project("Optional VST", prism_version="test", _script=project_script)
    track = song.track("Lead", role="lead").midi("C4 E4 G4", instrument=VST3("missing"))
    song.section("Only", bars=1, tracks=[track])

    context = inspect_agent_context(song)
    plugin = context["plugins"]["instances"][0]  # type: ignore[index]
    assert plugin["format"] == "vst3"
    assert plugin["available"] is False
    assert context["render_capabilities"]["missing_optional_plugins"] == 1  # type: ignore[index]
    assert context["render_capabilities"]["requires_network"] is False  # type: ignore[index]


def test_build_agent_operation_reloads_ids_and_cli_is_machine_readable(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "song"
    root.mkdir()
    (root / "main.py").write_text(
        "from prism import Project\n\n"
        "def build() -> Project:\n"
        "    song = Project('Reloadable', prism_version='test', "
        "project_id='reload-song', _script=__file__)\n"
        "    track = song.track('Lead', track_id='reload-track').midi('C4 E4 G4')\n"
        "    song.section('Only', section_id='reload-section', bars=1, tracks=[track])\n"
        "    return song\n",
        encoding="utf-8",
    )
    first = build_agent_operation(root, {"operation": "inspect"})
    second = build_agent_operation(root, {"operation": "inspect"})
    assert first["status"] == second["status"] == "ok"
    assert first["project_id"] == second["project_id"] == "reload-song"
    assert first["result"]["arrangement"]["tracks"][0]["id"] == "reload-track"  # type: ignore[index]
    assert first["revision_id"] == second["revision_id"]

    assert main(["agent", "inspect", str(root), "--json"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["contract"] == "prism.agent"
    assert output["result"]["revision_id"] == first["revision_id"]


def test_legacy_configuration_gets_deterministic_identity_migration() -> None:
    migrated = migrate_project_configuration(
        {
            "schema_version": 10,
            "name": "Old",
            "tracks": [
                {"name": "Bass", "clips": [{"kind": "midi"}]},
                {"name": "Pad", "clips": [{"kind": "midi"}]},
            ],
            "sections": [{"name": "Verse", "tracks": ["Bass", "Pad"]}],
        }
    )
    assert migrated["identity_schema_version"] == 1
    assert migrated["tracks"][0]["id"] == "project:main/track:0001"  # type: ignore[index]
    assert migrated["tracks"][1]["clips"][0]["id"] == (  # type: ignore[index]
        "project:main/track:0002/clip:0001"
    )
    assert migrated["sections"][0]["track_ids"] == [  # type: ignore[index]
        "project:main/track:0001",
        "project:main/track:0002",
    ]

    with pytest.raises(ProjectError, match="identity schema"):
        migrate_project_configuration({"schema_version": 11, "identity_schema_version": 2})


def test_revision_id_is_stable_for_the_same_built_revision(project_script: Path) -> None:
    song = _duplicate_name_project(project_script)
    assert project_revision_id(song) == project_revision_id(song)


def test_agent_capabilities_and_request_validation_are_structured(
    project_script: Path,
) -> None:
    song = _duplicate_name_project(project_script)

    bare = agent_capabilities(limits={"max_tracks": 2})
    assert bare["project_id"] is None
    assert bare["limits"]["max_tracks"] == 2  # type: ignore[index]
    assert bare["execution"]["requires_audio_device"] is False  # type: ignore[index]
    project_capabilities = song.agent_capabilities(
        limits=AgentLimits(max_tracks=3, max_notes=7)
    )
    assert project_capabilities["project_id"] == "fixture-song"
    assert project_capabilities["limits"]["max_notes"] == 7  # type: ignore[index]

    request = AgentOperationRequest.from_mapping(
        {
            "operation": "INSPECT",
            "selector": None,
            "limits": {"max_sections": 1},
            "expected_revision_id": "revision-from-before",
        }
    )
    assert request.operation == "inspect"
    assert request.selection == {}
    assert request.limits.max_sections == 1
    assert request.revision_id == "revision-from-before"
    assert AgentOperationRequest.from_mapping(request) is request
    assert song.agent_operation(AgentOperationRequest(operation="inspect"))["status"] == "ok"
    assert agent_operation(song, {"operation": "capabilities"})["status"] == "ok"

    with pytest.raises(AgentError, match="between 1 and 100000"):
        AgentLimits.from_mapping({"max_notes": 0})
    with pytest.raises(AgentError, match="must be an integer"):
        AgentLimits.from_mapping({"max_notes": True})
    with pytest.raises(AgentError, match="must be an object"):
        AgentOperationRequest.from_mapping("not an object")  # type: ignore[arg-type]
    with pytest.raises(AgentError, match="must be an integer"):
        AgentOperationRequest.from_mapping({"operation": "inspect", "schema_version": True})
    with pytest.raises(AgentError, match="must be a string"):
        AgentOperationRequest.from_mapping({"operation": 3})  # type: ignore[arg-type]
    with pytest.raises(AgentError, match="not supported"):
        AgentOperationRequest.from_mapping({"operation": "edit"})
    with pytest.raises(AgentError, match="must be an object"):
        AgentOperationRequest.from_mapping({"operation": "inspect", "selection": []})
    with pytest.raises(AgentError, match="must be an object"):
        AgentOperationRequest.from_mapping({"operation": "inspect", "limits": []})
    with pytest.raises(AgentError, match="must be a string"):
        AgentOperationRequest.from_mapping({"operation": "inspect", "revision_id": 1})

    invalid_instance = AgentOperationRequest(
        operation="inspect", schema_version=99  # type: ignore[arg-type]
    )
    with pytest.raises(AgentError, match="not supported"):
        AgentOperationRequest.from_mapping(invalid_instance)
    invalid_operation = AgentOperationRequest(
        operation="edit"  # type: ignore[arg-type]
    )
    with pytest.raises(AgentError, match="not supported"):
        AgentOperationRequest.from_mapping(invalid_operation)


def test_context_reports_all_clip_kinds_routing_assets_and_truncation(
    project_script: Path,
    sample_file: Path,
) -> None:
    song = Project(
        "Media fixture",
        prism_version="test",
        project_id="media-song",
        _script=project_script,
    )
    sample_track = song.track("Bass")
    sample_track.sample(
        "sounds/kick.wav",
        bars=1,
        clip_definition_id="sample-definition",
    )
    sample_track.sample(
        "sounds/kick.wav",
        bars=1,
        section="A",
        repeat=False,
        clip_definition_id="scoped-sample-definition",
    )
    song.track("Texture").audio(
        "sounds/kick.wav",
        bars=1,
        loop=False,
        repeat=False,
        clip_definition_id="audio-definition",
    )
    drum_track = song.track("Drums").drum(
        "kick",
        "x--- x---",
        bars=1,
        clip_definition_id="drum-definition",
    )
    lead_track = song.track("Lead", role="lead").midi(
        "C4 - E4 -",
        bars=1,
        clip_definition_id="lead-definition",
        pitch_bend=[(0.0, 0.0), (2.0, 1.0)],
        modulation=[(0.0, 0.1), (2.0, 0.8)],
    )
    lead_track.effect("gain", gain_db=-3.0)
    bus = song.bus("FX", bus_id="bus-fx", tracks=[lead_track])
    bus.effect("reverb", mix=0.25)
    sample_track.send(bus, gain_db=-9.0)
    song.master_effect("gain", gain_db=-1.0)
    song.section("A", section_id="section-a", bars=2, tracks=[sample_track, drum_track])
    song.section("B", section_id="section-b", bars=1, tracks=[lead_track])

    context = inspect_agent_context(
        song,
        limits={
            "max_sections": 1,
            "max_clip_definitions": 3,
            "max_plugins": 3,
            "max_parameters": 1,
        },
    )
    arrangement = context["arrangement"]  # type: ignore[assignment]
    assert [item["kind"] for item in arrangement["clip_definitions"]] == [  # type: ignore[index]
        "sample",
        "sample",
        "audio",
    ]
    assert "sections" in context["bounds"]["truncated"]  # type: ignore[index]
    assert "clip_definitions" in context["bounds"]["truncated"]  # type: ignore[index]
    assert "plugins" in context["bounds"]["truncated"]  # type: ignore[index]
    assert "parameters" in context["bounds"]["truncated"]  # type: ignore[index]
    instances = arrangement["clip_instances"]  # type: ignore[index]
    assert len(instances) >= 3
    assert len({item["id"] for item in instances}) == len(instances)
    assert any(item["source"] == "arrangement" for item in instances)
    assert arrangement["controllers"]  # type: ignore[index]
    assert arrangement["controller_boundary"] == "reset"  # type: ignore[index]
    assert context["musical_context"]["authored"]["key"] is None  # type: ignore[index]
    assert context["musical_context"]["inferred"]["harmony"]["source"] == "inferred"  # type: ignore[index]
    tracks = arrangement["tracks"]  # type: ignore[index]
    assert tracks[0]["role"]["value"] == "bass"  # type: ignore[index]
    assert tracks[1]["role"]["value"] == "unknown"  # type: ignore[index]
    assert tracks[0]["section_ids"] == ["section-a"]  # type: ignore[index]
    assert context["routing"]["buses"][0]["id"] == "bus-fx"  # type: ignore[index]
    assert context["routing"]["tracks"][0]["sends"][0]["bus_id"] == "bus-fx"  # type: ignore[index]
    assert context["plugins"]["available_instruments"]  # type: ignore[index]
    assert context["plugins"]["available_effects"]  # type: ignore[index]
    assert context["render_capabilities"]["can_render_native"] is True  # type: ignore[index]
    assert context["assets"][0]["path"] == "sounds/kick.wav"  # type: ignore[index]


def test_context_reports_vst_metadata_registry_and_missing_state_assets(tmp_path: Path) -> None:
    root = tmp_path / "vst-song"
    root.mkdir()
    script = root / "main.py"
    script.write_text("# VST fixture\n", encoding="utf-8")
    plugin_file = root / "plugins" / "Synth.vst3"
    plugin_file.parent.mkdir()
    plugin_file.write_bytes(b"fixture-vst")
    VSTRegistry(root).initialize()
    VSTRegistry(root).add("registered", plugin_file)
    state = root / "plugin-states" / "lead.state"
    state.parent.mkdir()
    state.write_bytes(b"state")
    song = Project("VST metadata", prism_version="test", _script=script)
    lead = song.track("Lead").midi(
        "C4",
        instrument=VST3(
            "registered",
            state="plugin-states/lead.state",
            parameters={"#4: Cutoff": 0.25},
            parameter_metadata=({"index": 4, "name": "Cutoff"},),
        ),
    )
    lead.effect(
        VST3(
            "missing",
            state="plugin-states/missing.state",
            parameters={"Unknown selector": 0.5},
            parameter_metadata=({"index": 7, "name": "Depth"},),
        )
    )
    song.section("Only", bars=1, tracks=[lead])

    context = inspect_agent_context(song)
    plugins = context["plugins"]["instances"]  # type: ignore[index]
    registered = plugins[0]
    missing = plugins[1]
    assert registered["available"] is True
    assert any(item["selector"] == "#4: Cutoff" for item in registered["parameters"])
    assert missing["available"] is False
    assert any("resolution_error" in item for item in missing["parameters"])
    assert context["plugins"]["available_vst3"][0]["alias"] == "registered"  # type: ignore[index]
    assert context["render_capabilities"]["external_plugins"] == 2  # type: ignore[index]
    assert context["render_capabilities"]["missing_optional_plugins"] == 1  # type: ignore[index]
    assert context["render_capabilities"]["can_render_native"] is False  # type: ignore[index]
    assets = {item["path"]: item for item in context["assets"]}  # type: ignore[index]
    assert assets["plugin-states/lead.state"]["exists"] is True
    assert assets["plugin-states/missing.state"]["exists"] is False


def test_selection_filters_and_invalid_ranges_remain_unambiguous(
    project_script: Path,
) -> None:
    song = _duplicate_name_project(project_script)

    by_role = song.agent_select({"entity": "tracks", "musical_role": "bass"})
    assert by_role["count"] == 1
    assert by_role["selected_ranges"] == [{"start_beat": 0.0, "end_beat": 8.0}]
    by_ids = song.agent_select(
        {"entity": "track", "ids": ["track-bass", "track-lead"]}
    )
    assert by_ids["count"] == 2
    by_project = song.agent_select({"entity": "project", "id": "fixture-song"})
    assert by_project["items"][0]["display_name"] == "Agent Fixture"  # type: ignore[index]
    by_bus = agent_operation(
        song,
        {"operation": "select", "selection": {"entity": "bus", "id": "missing-bus"}},
    )
    assert by_bus["error"]["code"] == "unknown_id"  # type: ignore[index]
    by_section = song.agent_select({"entity": "section", "name": "Verse"})
    assert by_section["items"][0]["id"] == "section-verse"  # type: ignore[index]
    by_range_object = song.agent_select(
        {
            "entity": "clip_instance",
            "section": "Verse",
            "range": {"start": 0, "end": 2},
        }
    )
    assert by_range_object["selected_ranges"] == [{"start_beat": 0.0, "end_beat": 2.0}]
    by_explicit_range = song.agent_select(
        {"entity": "note", "start_beat": 0, "end_beat": 1}
    )
    assert by_explicit_range["count"] >= 1

    invalid_cases = (
        ({"entity": "track", "ids": "track-bass"}, "invalid_selection"),
        ({"entity": "track", "id": 1}, "invalid_selection"),
        ({"entity": "track", "name": 1}, "invalid_selection"),
        ({"entity": "track", "role": 1}, "invalid_selection"),
        ({"entity": "track", "section": 1}, "invalid_selection"),
        ({"entity": "track", "range": [1]}, "invalid_range"),
        ({"entity": "track", "start_beat": 2}, "invalid_range"),
        ({"entity": "track", "range": [2, 1]}, "invalid_range"),
        ({"entity": "track", "section": "Missing"}, "unknown_id"),
        ({"entity": "track", "role": "not-a-role"}, "no_match"),
        ({"entity": "unknown"}, "unsupported_entity_type"),
        ({"entity": 1}, "invalid_selection"),
    )
    for selection, code in invalid_cases:
        result = agent_operation(song, {"operation": "select", "selection": selection})
        assert result["status"] == "error"
        assert result["error"]["code"] == code  # type: ignore[index]


def test_agent_build_and_cli_error_paths_are_machine_readable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    no_contract = tmp_path / "no-contract"
    no_contract.mkdir()
    (no_contract / "main.py").write_text("from prism import Project\n", encoding="utf-8")
    contract_error = build_agent_operation(no_contract)
    assert contract_error["status"] == "error"
    assert contract_error["error"]["code"] == "build_contract_required"  # type: ignore[index]

    not_project = tmp_path / "not-project"
    not_project.mkdir()
    build_error = build_agent_operation(not_project, {"operation": "inspect"})
    assert build_error["error"]["code"] == "build_error"  # type: ignore[index]

    assert main(["agent", "capabilities", "--limits", "{\"max_tracks\": 1}"]) == 0
    capabilities = json.loads(capsys.readouterr().out)
    assert capabilities["limits"]["max_tracks"] == 1
    assert main(["agent", "capabilities", "--limits", "[]"]) == 1
    invalid_cli = json.loads(capsys.readouterr().out)
    assert invalid_cli["error"]["code"] == "invalid_cli_request"
