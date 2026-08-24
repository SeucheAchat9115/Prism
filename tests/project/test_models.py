from uuid import uuid4

import pytest
from pydantic import ValidationError

from prism.project.models import (
    AssetReference,
    AudioClip,
    ClipSlot,
    Project,
    Scene,
    Track,
    new_project,
)
from prism.project.validation import project_reference_issues


def test_new_project_has_schema_and_transport_defaults() -> None:
    project = new_project("Demo")

    assert project.schema_version == 2
    assert project.revision.number == 0
    assert project.transport.tempo_bpm == 120
    assert project.transport.sample_rate == 44100


def test_models_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        Track(name="Drums", unknown_field=True)


def test_asset_member_path_must_be_safe() -> None:
    with pytest.raises(ValidationError):
        AssetReference(
            member_path="../outside.wav",
            original_name="outside.wav",
            size_bytes=1,
            sha256="0" * 64,
            sample_rate=8000,
            channels=1,
            frames=1,
            format="WAV",
        )


def test_project_reference_validation_reports_json_paths() -> None:
    track = Track(name="Drums")
    scene = Scene(name="Intro")
    clip = AudioClip(name="Kick", asset_id=uuid4())
    project = Project(
        name="Demo",
        tracks=[track],
        scenes=[scene],
        clips=[clip],
        clip_slots=[ClipSlot(track_id=track.id, scene_id=scene.id, clip_id=clip.id)],
    )

    issues = project_reference_issues(project)

    assert any(issue.code == "missing_asset_reference" for issue in issues)
