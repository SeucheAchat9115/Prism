from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from prism.cli import app
from prism.demo import demo_ids
from prism.project import ProjectRepository


def test_one_command_demo_is_device_free_and_reopenable(tmp_path: Path) -> None:
    path = tmp_path / "demo.prism-work"
    runner = CliRunner()

    created = runner.invoke(app, ["demo", str(path), "--no-serve"])
    reopened = runner.invoke(app, ["demo", str(path), "--no-serve"])

    assert created.exit_code == 0, created.output
    assert reopened.exit_code == 0, reopened.output
    with ProjectRepository.open(path) as repository:
        project = repository.get_project()
        assert project.revision.number == 1
        assert len(project.tracks) == 2
        assert len(project.scenes) == 2
        assert len(project.assets) == 2
        assert len(project.clips) == 4
        assert len(project.clip_slots) == 4
        assert project.transport.tempo_bpm == 120.0
        assert project.transport.quantization == "bar"
        assert project.transport.sample_rate == 44_100

        ids = demo_ids(project.project_id)
        tracks = {track.id: track for track in project.tracks}
        assert [(track.name, track.order) for track in project.tracks] == [
            ("Drums", 0),
            ("Synth", 1),
        ]
        assert [(scene.name, scene.order) for scene in project.scenes] == [
            ("Verse", 0),
            ("Chorus", 1),
        ]
        assert tracks[ids["drums"]].mixer.model_dump() == {
            "gain_db": -3.0,
            "pan": -0.25,
            "muted": False,
            "solo": False,
        }
        assert tracks[ids["synth"]].mixer.model_dump() == {
            "gain_db": -9.0,
            "pan": 0.25,
            "muted": True,
            "solo": False,
        }
        assert {clip.id for clip in project.clips} == {
            ids["kick-clip"],
            ids["tone-clip"],
            ids["chorus-kick-clip"],
            ids["chorus-tone-clip"],
        }
        assert {slot.id for slot in project.clip_slots} == {
            ids["kick-slot"],
            ids["tone-slot"],
            ids["chorus-kick-slot"],
            ids["chorus-tone-slot"],
        }
