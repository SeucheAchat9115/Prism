from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from vibesound.project import create_project, import_audio, load_project, save_project
from vibesound.project.models import AudioClip, ClipSlot, Scene, Track


def make_archive_fixture(
    directory: Path,
) -> tuple[Path, object, Track, Scene, AudioClip]:
    directory.mkdir(parents=True, exist_ok=True)
    source_path = directory / "source.wav"
    project_path = directory / "fixture.vibesound"
    sf.write(
        source_path,
        np.ones(16, dtype=np.float32),
        8,
        format="WAV",
        subtype="FLOAT",
    )
    create_project(project_path, "Application fixture", sample_rate=8)
    asset = import_audio(project_path, source_path)
    project = load_project(project_path)
    track = Track(name="Track")
    scene = Scene(name="Scene")
    clip = AudioClip(name="Clip", asset_id=asset.id, loop=True)
    project.tracks.append(track)
    project.scenes.append(scene)
    project.clips.append(clip)
    project.clip_slots.append(ClipSlot(track_id=track.id, scene_id=scene.id, clip_id=clip.id))
    save_project(project_path, project)
    return project_path, load_project(project_path), track, scene, clip
