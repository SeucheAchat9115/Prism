"""Fixtures shared by offline renderer tests."""

from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import uuid4

import numpy as np
import soundfile as sf

from vibesound.engine import AudioBuffer, InMemoryClipSourceProvider
from vibesound.project import create_project, import_audio, load_project, save_project
from vibesound.project.models import (
    AssetReference,
    AudioClip,
    ClipSlot,
    Project,
    Scene,
    Track,
    TransportState,
)


def make_memory_project(
    samples: np.ndarray,
    *,
    sample_rate: int = 8,
    tempo_bpm: float = 120.0,
    quantization: str = "bar",
) -> tuple[Project, InMemoryClipSourceProvider, Track, Scene, AudioClip]:
    array = np.asarray(samples, dtype=np.float32)
    if array.ndim == 1:
        array = array[:, None]
    asset_id = uuid4()
    clip_id = uuid4()
    track = Track(name="Track")
    scene = Scene(name="Scene")
    clip = AudioClip(id=clip_id, name="Clip", asset_id=asset_id)
    payload = array.tobytes()
    asset = AssetReference(
        id=asset_id,
        member_path=f"assets/audio/{asset_id}.wav",
        original_name="fixture.wav",
        size_bytes=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
        sample_rate=sample_rate,
        channels=array.shape[1],
        frames=array.shape[0],
        format="WAV",
    )
    project = Project(
        name="Render fixture",
        transport=TransportState(
            tempo_bpm=tempo_bpm,
            sample_rate=sample_rate,
            quantization=quantization,
        ),
        tracks=[track],
        scenes=[scene],
        clips=[clip],
        clip_slots=[ClipSlot(track_id=track.id, scene_id=scene.id, clip_id=clip.id)],
        assets=[asset],
    )
    provider = InMemoryClipSourceProvider({asset_id: AudioBuffer(sample_rate, array)})
    return project, provider, track, scene, clip


def make_archive_project(
    directory: Path,
    samples: np.ndarray,
    *,
    source_rate: int = 8,
    project_rate: int = 8,
    source_offset_frames: int = 0,
    duration_frames: int | None = None,
) -> tuple[Path, Project, Track, Scene, AudioClip]:
    project_path = directory / "fixture.vibesound"
    source_path = directory / "source.wav"
    array = np.asarray(samples, dtype=np.float32)
    sf.write(source_path, array, source_rate, format="WAV", subtype="FLOAT")
    create_project(project_path, "Archive render fixture", sample_rate=project_rate)
    asset = import_audio(project_path, source_path)
    project = load_project(project_path)
    track = Track(name="Track")
    scene = Scene(name="Scene")
    clip = AudioClip(
        name="Clip",
        asset_id=asset.id,
        source_offset_frames=source_offset_frames,
        duration_frames=duration_frames,
    )
    project.tracks.append(track)
    project.scenes.append(scene)
    project.clips.append(clip)
    project.clip_slots.append(ClipSlot(track_id=track.id, scene_id=scene.id, clip_id=clip.id))
    save_project(project_path, project)
    return project_path, load_project(project_path), track, scene, clip
