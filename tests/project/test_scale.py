from __future__ import annotations

import time
from pathlib import Path

from prism.project import ProjectRepository, create_project, import_audio
from prism.project.models import ClipSlot, Scene, Track

from ._helpers import write_wav


def test_representative_50_track_metadata_commit_does_not_rewrite_audio(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "large.prism"
    audio = tmp_path / "large-source.wav"
    write_wav(audio, frames=8000, sample_rate=8000)
    create_project(archive, "Representative scale", sample_rate=8000)
    import_audio(archive, audio)

    with ProjectRepository.open(archive) as repository:
        project = repository.get_project()
        project.tracks = [Track(name=f"Track {index + 1}", order=index) for index in range(50)]
        project.scenes = [Scene(name=f"Scene {index + 1}", order=index) for index in range(50)]
        project.clip_slots = [
            ClipSlot(track_id=track.id, scene_id=scene.id)
            for track in project.tracks
            for scene in project.scenes
        ]
        project.revision.number += 1
        started = time.monotonic()
        repository.commit_project(project, history={"kind": "scale_fixture"})
        elapsed = time.monotonic() - started

        asset_path = repository.asset_path(project.assets[0])
        before = (asset_path.stat().st_mtime_ns, asset_path.read_bytes())
        scalar = repository.get_project()
        scalar.name = "Scalar edit"
        scalar.revision.number += 1
        repository.commit_project(scalar, history={"kind": "scalar"})
        after = (asset_path.stat().st_mtime_ns, asset_path.read_bytes())

        assert elapsed < 5.0
        assert before == after
