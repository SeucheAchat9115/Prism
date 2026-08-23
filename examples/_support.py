"""Shared setup helpers for the manually runnable Prism examples."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import numpy as np
import soundfile as sf

from prism.engine import AudioBuffer, InMemoryClipSourceProvider
from prism.project import create_project, import_audio, load_project, save_project
from prism.project.models import (
    AssetReference,
    AudioClip,
    ClipSlot,
    MixerState,
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
    return write_audio_wav(path, values, sample_rate)


def write_audio_wav(path: Path, samples: np.ndarray, sample_rate: int) -> int:
    """Write finite mono or stereo float samples as a portable PCM WAV."""

    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")
    array = np.asarray(samples, dtype=np.float32)
    if array.ndim not in (1, 2) or array.shape[0] <= 0:
        raise ValueError("samples must contain non-empty mono or stereo frames")
    if array.ndim == 2 and array.shape[1] not in (1, 2):
        raise ValueError("samples must be mono or stereo")
    if not np.isfinite(array).all():
        raise ValueError("samples must be finite")
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, np.clip(array, -1.0, 1.0), sample_rate, format="WAV", subtype="PCM_16")
    return array.shape[0]


def _add_decaying_tone(
    output: np.ndarray,
    sample_rate: int,
    start_seconds: float,
    frequency: float,
    *,
    amplitude: float,
    decay: float,
    duration: float,
) -> None:
    """Add one deterministic percussive tone to a mono buffer in place."""

    start = int(round(start_seconds * sample_rate))
    if start >= output.shape[0]:
        return
    length = min(output.shape[0] - start, max(1, int(round(duration * sample_rate))))
    timeline = np.arange(length, dtype=np.float64) / sample_rate
    envelope = np.exp(-decay * timeline)
    output[start : start + length] += np.asarray(
        amplitude * envelope * np.sin(2.0 * math.pi * frequency * timeline),
        dtype=np.float32,
    )


def _make_kick(sample_rate: int) -> np.ndarray:
    output = np.zeros(sample_rate, dtype=np.float32)
    for start in (0.0, 0.5):
        _add_decaying_tone(
            output,
            sample_rate,
            start,
            78.0,
            amplitude=0.85,
            decay=11.0,
            duration=0.28,
        )
    return output


def _make_snare(sample_rate: int) -> np.ndarray:
    output = np.zeros(sample_rate, dtype=np.float32)
    rng = np.random.default_rng(11)
    for start in (0.25, 0.75):
        frame = int(round(start * sample_rate))
        length = min(sample_rate - frame, int(round(0.18 * sample_rate)))
        timeline = np.arange(length, dtype=np.float64) / sample_rate
        envelope = np.exp(-20.0 * timeline)
        noise = rng.standard_normal(length) * 0.34
        tone = 0.18 * np.sin(2.0 * math.pi * 190.0 * timeline)
        output[frame : frame + length] += np.asarray((noise + tone) * envelope, dtype=np.float32)
    return output


def _make_hats(sample_rate: int) -> np.ndarray:
    output = np.zeros(sample_rate, dtype=np.float32)
    rng = np.random.default_rng(17)
    for index in range(8):
        frame = int(round(index * sample_rate / 8))
        length = min(sample_rate - frame, int(round(0.07 * sample_rate)))
        timeline = np.arange(length, dtype=np.float64) / sample_rate
        envelope = np.exp(-65.0 * timeline)
        output[frame : frame + length] += np.asarray(
            rng.standard_normal(length) * 0.18 * envelope,
            dtype=np.float32,
        )
    return output


def _make_bass(sample_rate: int) -> np.ndarray:
    seconds = 2.0
    output = np.zeros(int(round(seconds * sample_rate)), dtype=np.float32)
    for start, frequency in ((0.0, 110.0), (0.5, 110.0), (1.0, 130.81), (1.5, 98.0)):
        frame = int(round(start * sample_rate))
        length = min(output.shape[0] - frame, int(round(0.42 * sample_rate)))
        timeline = np.arange(length, dtype=np.float64) / sample_rate
        envelope = np.minimum(timeline * 40.0, 1.0) * np.exp(-2.6 * timeline)
        output[frame : frame + length] += np.asarray(
            0.42 * envelope * np.sin(2.0 * math.pi * frequency * timeline),
            dtype=np.float32,
        )
    return output


def _make_pad(sample_rate: int) -> np.ndarray:
    frames = 2 * sample_rate
    timeline = np.arange(frames, dtype=np.float64) / sample_rate
    attack = np.minimum(timeline * 3.0, 1.0)
    release = np.minimum((frames - np.arange(frames)) / sample_rate * 3.0, 1.0)
    envelope = np.minimum(attack, release)
    chord = (
        np.sin(2.0 * math.pi * 220.0 * timeline)
        + np.sin(2.0 * math.pi * 277.18 * timeline)
        + np.sin(2.0 * math.pi * 329.63 * timeline)
    ) / 3.0
    return np.asarray(0.20 * envelope * chord, dtype=np.float32)


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
        name="Prism Example",
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
    project_path = directory / "example.prism"
    write_sine_wav(source_path, sample_rate=sample_rate, seconds=seconds)
    create_project(project_path, "Prism Example", tempo_bpm=120.0, sample_rate=sample_rate)
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


def make_music_fixture(
    directory: Path,
    *,
    sample_rate: int = 8000,
) -> tuple[Path, Project, dict[str, Track], dict[str, Scene], dict[str, AudioClip]]:
    """Create a small multi-track, multi-scene beat for runnable examples."""

    directory.mkdir(parents=True, exist_ok=True)
    project_path = directory / "demo-beat.prism"
    create_project(project_path, "Prism Demo Beat", tempo_bpm=120.0, sample_rate=sample_rate)

    waveforms = {
        "kick": _make_kick(sample_rate),
        "snare": _make_snare(sample_rate),
        "hats": _make_hats(sample_rate),
        "bass": _make_bass(sample_rate),
        "pad": _make_pad(sample_rate),
    }
    assets = {}
    for name, samples in waveforms.items():
        source_path = directory / f"{name}.wav"
        write_audio_wav(source_path, samples, sample_rate)
        assets[name] = import_audio(project_path, source_path)

    project = load_project(project_path)
    track_definitions = (
        ("Kick", "kick", -3.0, 0.0),
        ("Snare", "snare", -6.0, 0.0),
        ("Hats", "hats", -12.0, 0.15),
        ("Bass", "bass", -6.0, -0.1),
        ("Pad", "pad", -12.0, 0.0),
    )
    tracks = {
        name: Track(
            name=name,
            order=index,
            mixer=MixerState(gain_db=gain_db, pan=pan),
        )
        for index, (name, _, gain_db, pan) in enumerate(track_definitions)
    }
    scenes = {
        name: Scene(name=name, order=index)
        for index, name in enumerate(("Intro", "Groove", "Breakdown", "Outro"))
    }
    project.tracks.extend(tracks.values())
    project.scenes.extend(scenes.values())

    assignments = {
        "Intro": {"Hats": "hats", "Pad": "pad"},
        "Groove": {name: asset_name for name, asset_name, _, _ in track_definitions},
        "Breakdown": {"Hats": "hats", "Pad": "pad"},
        "Outro": {"Kick": "kick", "Hats": "hats", "Bass": "bass"},
    }
    clips: dict[str, AudioClip] = {}
    for scene_name, track_assignments in assignments.items():
        scene = scenes[scene_name]
        for track_name, asset_name in track_assignments.items():
            track = tracks[track_name]
            clip = AudioClip(
                name=f"{scene_name} {track_name}",
                asset_id=assets[asset_name].id,
                loop=True,
            )
            project.clips.append(clip)
            project.clip_slots.append(
                ClipSlot(track_id=track.id, scene_id=scene.id, clip_id=clip.id)
            )
            clips[f"{scene_name}:{track_name}"] = clip
    save_project(project_path, project)
    return project_path, load_project(project_path), tracks, scenes, clips


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
