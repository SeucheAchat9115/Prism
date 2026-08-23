"""Fixtures for deterministic session engine tests."""

from __future__ import annotations

import hashlib
from uuid import UUID, uuid4

import numpy as np
from numpy.typing import NDArray

from prism.engine import AudioBuffer, InMemoryClipSourceProvider
from prism.project.models import (
    AssetReference,
    AudioClip,
    ClipSlot,
    Project,
    Scene,
    Track,
    TransportState,
)

Float32Array = NDArray[np.float32]


def make_project(
    samples: Float32Array,
    *,
    sample_rate: int = 8,
    tempo_bpm: float = 120.0,
    quantization: str = "none",
    source_offset_frames: int = 0,
    duration_frames: int | None = None,
    loop: bool = False,
    track: Track | None = None,
    scene: Scene | None = None,
    clip_id: UUID | None = None,
    asset_id: UUID | None = None,
) -> tuple[Project, InMemoryClipSourceProvider, Track, Scene, AudioClip]:
    array = np.asarray(samples, dtype=np.float32)
    if array.ndim == 1:
        array = array[:, None]
    asset_id = asset_id or uuid4()
    clip_id = clip_id or uuid4()
    track = track or Track(name="Track")
    scene = scene or Scene(name="Scene")
    clip = AudioClip(
        id=clip_id,
        name="Clip",
        asset_id=asset_id,
        source_offset_frames=source_offset_frames,
        duration_frames=duration_frames,
        loop=loop,
    )
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
        name="Engine fixture",
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
