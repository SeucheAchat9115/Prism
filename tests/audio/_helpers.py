"""Fixtures for audio backend tests."""

from __future__ import annotations

import hashlib
from uuid import uuid4

import numpy as np

from vibesound.engine import AudioBuffer, InMemoryClipSourceProvider
from vibesound.project.models import (
    AssetReference,
    AudioClip,
    ClipSlot,
    Project,
    Scene,
    Track,
    TransportState,
)


def make_audio_fixture(
    *,
    frames: int = 32,
    sample_rate: int = 8,
    samples: np.ndarray | None = None,
):
    values = (
        np.ones(frames, dtype=np.float32)
        if samples is None
        else np.asarray(samples, dtype=np.float32)
    )
    if values.ndim != 1 or values.shape[0] <= 0:
        raise ValueError("Audio fixture samples must be a non-empty mono array")
    frames = values.shape[0]
    asset_id = uuid4()
    clip_id = uuid4()
    track = Track(name="Track")
    scene = Scene(name="Scene")
    clip = AudioClip(id=clip_id, name="Clip", asset_id=asset_id)
    payload = values[:, None].tobytes()
    asset = AssetReference(
        id=asset_id,
        member_path=f"assets/audio/{asset_id}.wav",
        original_name="fixture.wav",
        size_bytes=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
        sample_rate=sample_rate,
        channels=1,
        frames=frames,
        format="WAV",
    )
    project = Project(
        name="Audio fixture",
        transport=TransportState(
            sample_rate=sample_rate,
            quantization="none",
        ),
        tracks=[track],
        scenes=[scene],
        clips=[clip],
        clip_slots=[ClipSlot(track_id=track.id, scene_id=scene.id, clip_id=clip.id)],
        assets=[asset],
    )
    provider = InMemoryClipSourceProvider(
        {asset_id: AudioBuffer(sample_rate, values[:, None])}
    )
    return project, provider, track, scene, clip


class FakeOutputStream:
    """Small OutputStream double that exposes the callback for unit tests."""

    instances: list["FakeOutputStream"] = []

    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs
        self.callback = kwargs["callback"]
        self.started = False
        self.stopped = False
        self.closed = False
        self.instances.append(self)

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def close(self) -> None:
        self.closed = True

    def pull(self, frames: int, status: object = None) -> np.ndarray:
        output = np.empty((frames, 2), dtype=np.float32)
        self.callback(output, frames, None, status)
        return output
