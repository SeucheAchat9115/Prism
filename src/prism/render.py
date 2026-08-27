"""Deterministic offline rendering for script-authored Prism projects."""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf
import soxr

from prism.errors import ProjectError, RenderError
from prism.music import db_gain
from prism.project.builder import AudioClip, DrumClip, MidiClip, Project, SampleClip, Track
from prism.synthesis.engine import render_native_synth
from prism.synthesis.types import NativeSynthSpec


@dataclass(frozen=True, slots=True)
class RenderResult:
    """Useful facts about one completed WAV and its reproducibility manifest."""

    path: Path
    manifest_path: Path
    sample_rate: int
    channels: int
    frames: int
    duration_seconds: float
    sha256: str
    peak_dbfs: float | None

    def __str__(self) -> str:
        return f"Rendered {self.duration_seconds:.2f}s to {self.path}"


def render_project(project: Project, output: str | Path) -> RenderResult:
    """Render every named section in order and write a stable project manifest."""

    try:
        summary = project.validate()
        output_path = project._output_path(output, suffix=".wav")
        buffers = {track.name: _track_buffer(project, track) for track in project.tracks}
        total_frames = summary.bars * project.frames_per_bar
        mix = np.zeros((total_frames, 2), dtype=np.float64)
        cursor = 0
        for section in project.sections:
            frames = section.bars * project.frames_per_bar
            active = (
                {track.name for track in project.tracks}
                if section.tracks is None
                else set(section.tracks)
            )
            for track in project.tracks:
                if track.muted or track.name not in active:
                    continue
                part = _loop_to(buffers[track.name], frames)
                mix[cursor : cursor + frames] += _mix_track(part, track)
            cursor += frames
        mix *= db_gain(project.master_gain_db)
        peak = float(np.max(np.abs(mix))) if mix.size else 0.0
        target = 10.0 ** (-1.0 / 20.0)
        if project.normalize and peak > target:
            mix *= target / peak
            peak = target
        mix = np.clip(mix, -1.0, 1.0)
        _write_wav(output_path, mix, project.sample_rate)
        digest = _sha256(output_path)
        manifest_path = project.root / ".prism" / "project.json"
        result = RenderResult(
            path=output_path,
            manifest_path=manifest_path,
            sample_rate=project.sample_rate,
            channels=2,
            frames=total_frames,
            duration_seconds=total_frames / project.sample_rate,
            sha256=digest,
            peak_dbfs=None if peak == 0.0 else 20.0 * math.log10(peak),
        )
        _write_manifest(project, result)
        return result
    except (ProjectError, RenderError):
        raise
    except (OSError, RuntimeError, ValueError) as error:
        raise RenderError(f"Could not render {project.name!r}: {error}") from error


def _track_buffer(project: Project, track: Track) -> np.ndarray:
    clip = track.clip
    assert clip is not None
    if isinstance(clip, SampleClip):
        source = _read_audio(project.root / clip.path, project.sample_rate)
        frames = clip.bars * project.frames_per_bar
        output = np.zeros((frames, 2), dtype=np.float64)
        boundaries = np.rint(np.linspace(0, frames, len(clip.pattern) + 1)).astype(np.int64)
        source = source * db_gain(clip.gain_db)
        for index, step in enumerate(clip.pattern):
            if step == "-":
                continue
            start = int(boundaries[index])
            length = min(source.shape[0], frames - start)
            output[start : start + length] += source[:length]
        return output
    if isinstance(clip, AudioClip):
        source = _read_audio(project.root / clip.path, project.sample_rate)
        source *= db_gain(clip.gain_db)
        frames = clip.bars * project.frames_per_bar
        return _loop_to(source, frames) if clip.loop else _fit_to(source, frames)
    if isinstance(clip, DrumClip):
        spec = NativeSynthSpec(
            preset=clip.preset,
            sequence=clip.pattern,
            bars=clip.bars,
            gain_db=clip.gain_db,
            seed=clip.seed,
        )
        return _synth_audio(project, spec)
    assert isinstance(clip, MidiClip)
    spec = NativeSynthSpec(
        preset=clip.instrument,
        sequence=clip.notes,
        bars=clip.bars,
        waveform=clip.waveform,
        attack_ms=clip.attack_ms,
        decay_ms=clip.decay_ms,
        sustain_level=clip.sustain,
        release_ms=clip.release_ms,
        cutoff_hz=clip.cutoff_hz,
        gate=clip.gate,
        gain_db=clip.gain_db,
    )
    return _synth_audio(project, spec) * (clip.velocity / 100.0)


def _synth_audio(project: Project, spec: NativeSynthSpec) -> np.ndarray:
    samples = render_native_synth(
        spec,
        sample_rate=project.sample_rate,
        tempo_bpm=project.tempo,
        beats_per_bar=project.beats_per_bar,
    )
    return np.repeat(samples[:, np.newaxis], 2, axis=1) / math.sqrt(2.0)


def _read_audio(path: Path, sample_rate: int) -> np.ndarray:
    try:
        decoded, source_rate = sf.read(path, dtype="float64", always_2d=True)
    except (OSError, RuntimeError) as error:
        raise RenderError(f"Could not read source audio {path.name!r}: {error}") from error
    samples = np.asarray(decoded, dtype=np.float64)
    if samples.shape[0] == 0:
        raise RenderError(f"Source audio is empty: {path.name}")
    if samples.shape[1] == 1:
        samples = np.repeat(samples, 2, axis=1) / math.sqrt(2.0)
    elif samples.shape[1] != 2:
        raise RenderError(f"Source audio must be mono or stereo: {path.name}")
    if source_rate != sample_rate:
        samples = np.asarray(
            soxr.resample(samples, source_rate, sample_rate, quality="HQ"),
            dtype=np.float64,
        )
    if not np.isfinite(samples).all():
        raise RenderError(f"Source audio contains non-finite samples: {path.name}")
    return np.asarray(samples, dtype=np.float64)


def _mix_track(samples: np.ndarray, track: Track) -> np.ndarray:
    output = samples * db_gain(track.gain_db)
    if track.pan < 0.0:
        output = output.copy()
        output[:, 1] *= 1.0 + track.pan
    elif track.pan > 0.0:
        output = output.copy()
        output[:, 0] *= 1.0 - track.pan
    return output


def _loop_to(source: np.ndarray, frames: int) -> np.ndarray:
    if source.shape[0] == frames:
        return source.copy()
    repeats = math.ceil(frames / source.shape[0])
    return np.asarray(np.tile(source, (repeats, 1))[:frames], dtype=np.float64).copy()


def _fit_to(source: np.ndarray, frames: int) -> np.ndarray:
    output = np.zeros((frames, 2), dtype=np.float64)
    length = min(frames, source.shape[0])
    output[:length] = source[:length]
    return output


def _write_wav(path: Path, samples: np.ndarray, sample_rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        os.close(descriptor)
        temporary = Path(name)
        sf.write(
            temporary,
            np.asarray(samples, dtype=np.float32),
            sample_rate,
            format="WAV",
            subtype="PCM_16",
        )
        with temporary.open("r+b") as stream:
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    except (OSError, RuntimeError, ValueError) as error:
        raise RenderError(f"Could not write WAV file {path}: {error}") from error
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _write_manifest(project: Project, result: RenderResult) -> None:
    document = project.configuration()
    document["sources"] = {
        path.relative_to(project.root).as_posix(): {
            "bytes": path.stat().st_size,
            "sha256": _sha256(path),
        }
        for path in sorted(project._sample_files(), key=lambda item: item.as_posix().casefold())
    }
    document["script_sha256"] = _sha256(project.script)
    document["render"] = {
        "path": result.path.relative_to(project.root).as_posix(),
        "format": "WAV",
        "subtype": "PCM_16",
        "sample_rate": result.sample_rate,
        "channels": result.channels,
        "frames": result.frames,
        "duration_seconds": result.duration_seconds,
        "sha256": result.sha256,
        "peak_dbfs": result.peak_dbfs,
    }
    payload = (json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()
    path = result.manifest_path
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    try:
        temporary.write_bytes(payload)
        os.replace(temporary, path)
    except OSError as error:
        raise RenderError(f"Could not write project manifest {path}: {error}") from error
    finally:
        temporary.unlink(missing_ok=True)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


__all__ = ["RenderResult"]
