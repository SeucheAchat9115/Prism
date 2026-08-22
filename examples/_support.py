"""Shared setup helpers for the manually runnable VibeSound examples."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import wave
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import numpy as np

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


def parse_output_dir(example_name: str, description: str) -> Path:
    """Create a unique output directory for an artifact-producing example."""

    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "output",
        help="Base directory for generated files; a unique run directory is created below it.",
    )
    args = parser.parse_args()
    base = args.output_dir.expanduser()
    run_dir = base / f"{example_name}-{datetime.now():%Y%m%d-%H%M%S}-{uuid4().hex[:6]}"
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def print_json(value: object) -> None:
    """Print example results in a readable, copyable form."""

    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str))


def write_sine_wav(
    path: Path,
    *,
    sample_rate: int = 8000,
    seconds: float = 1.0,
    frequency: float = 440.0,
    amplitude: float = 0.25,
) -> int:
    """Write a small mono PCM WAV and return its frame count."""

    if seconds <= 0 or sample_rate <= 0:
        raise ValueError("seconds and sample_rate must be positive")
    frames = max(1, int(round(sample_rate * seconds)))
    timeline = np.arange(frames, dtype=np.float64) / sample_rate
    values = np.clip(amplitude * np.sin(2.0 * math.pi * frequency * timeline), -1.0, 1.0)
    pcm = np.asarray(np.rint(values * 32767.0), dtype="<i2")
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        audio.writeframes(pcm.tobytes())
    return frames


def make_memory_fixture(
    *,
    sample_rate: int = 8000,
    seconds: float = 2.0,
    tempo_bpm: float = 120.0,
    quantization: str = "none",
    loop: bool = True,
) -> tuple[Project, InMemoryClipSourceProvider, Track, Scene, AudioClip]:
    """Build a project and injected source provider for engine/backend examples."""

    frames = max(1, int(round(sample_rate * seconds)))
    timeline = np.arange(frames, dtype=np.float64) / sample_rate
    values = (0.25 * np.sin(2.0 * math.pi * 220.0 * timeline)).astype(np.float32)
    mono = values[:, None]
    asset_id = uuid4()
    clip_id = uuid4()
    track = Track(name="Example Track")
    scene = Scene(name="Example Scene")
    clip = AudioClip(
        id=clip_id,
        name="Example Sine",
        asset_id=asset_id,
        loop=loop,
    )
    payload = mono.tobytes()
    asset = AssetReference(
        id=asset_id,
        member_path=f"assets/audio/{asset_id}.wav",
        original_name="example-sine.wav",
        size_bytes=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
        sample_rate=sample_rate,
        channels=1,
        frames=frames,
        format="WAV",
    )
    project = Project(
        name="VibeSound Example",
        transport=TransportState(
            tempo_bpm=tempo_bpm,
            sample_rate=sample_rate,
            quantization=quantization,  # type: ignore[arg-type]
        ),
        tracks=[track],
        scenes=[scene],
        clips=[clip],
        clip_slots=[ClipSlot(track_id=track.id, scene_id=scene.id, clip_id=clip.id)],
        assets=[asset],
    )
    provider = InMemoryClipSourceProvider({asset_id: AudioBuffer(sample_rate, mono)})
    return project, provider, track, scene, clip


def make_archive_fixture(
    directory: Path,
    *,
    sample_rate: int = 8000,
    seconds: float = 1.0,
    loop: bool = False,
) -> tuple[Path, Project, Track, Scene, AudioClip]:
    """Create a self-contained archive with one generated audio clip."""

    directory.mkdir(parents=True, exist_ok=True)
    source_path = directory / "source.wav"
    project_path = directory / "example.vibesound"
    write_sine_wav(source_path, sample_rate=sample_rate, seconds=seconds)
    create_project(project_path, "VibeSound Example", tempo_bpm=120.0, sample_rate=sample_rate)
    asset = import_audio(project_path, source_path)
    project = load_project(project_path)
    track = Track(name="Example Track")
    scene = Scene(name="Example Scene")
    clip = AudioClip(name="Example Sine", asset_id=asset.id, loop=loop)
    project.tracks.append(track)
    project.scenes.append(scene)
    project.clips.append(clip)
    project.clip_slots.append(ClipSlot(track_id=track.id, scene_id=scene.id, clip_id=clip.id))
    save_project(project_path, project)
    return project_path, load_project(project_path), track, scene, clip


def action_summary(action: object) -> dict[str, object]:
    """Serialize a ScheduledAction without depending on its dataclass repr."""

    return {
        "target_frame": getattr(action, "target_frame"),
        "affected_track_ids": [str(item) for item in getattr(action, "affected_track_ids")],
        "changed": getattr(action, "changed"),
    }


def event_summary(events: tuple[object, ...]) -> list[dict[str, object]]:
    """Keep engine event output compact and JSON-friendly."""

    result: list[dict[str, object]] = []
    for event in events:
        item: dict[str, object] = {
            "kind": getattr(event, "kind"),
            "frame": getattr(event, "frame"),
        }
        mode = getattr(event, "mode", None)
        if mode is not None:
            item["mode"] = getattr(mode, "value", str(mode))
        result.append(item)
    return result
