"""Archive decoding, deterministic resampling, and private render snapshots."""

from __future__ import annotations

import hashlib
import io
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID
from zipfile import BadZipFile, ZipFile

import numpy as np
import soundfile as sf
import soxr

from vibesound.engine import AudioBuffer, ClipSourceProvider, InMemoryClipSourceProvider
from vibesound.project.models import AssetReference, Project
from vibesound.project.repository import RepositorySnapshot
from vibesound.rendering.errors import RenderValidationError


@dataclass(frozen=True, slots=True)
class PreparedRenderProject:
    """A private project/source pair ready for the Phase 2 session engine."""

    project: Project
    sources: InMemoryClipSourceProvider


@dataclass(frozen=True, slots=True)
class _PreparedAsset:
    buffer: AudioBuffer
    source_rate: int


def resample_linear(
    samples: np.ndarray,
    source_rate: int,
    target_rate: int,
) -> np.ndarray:
    """Resample mono/stereo samples with deterministic linear interpolation.

    The output length is ``ceil(source_frames * target_rate / source_rate)``.
    Positions are evaluated at ``m * source_rate / target_rate`` and clamped to
    the final source frame, which makes the result stable for short clips too.
    """

    if not isinstance(source_rate, int) or isinstance(source_rate, bool) or source_rate <= 0:
        raise RenderValidationError("Audio source sample rate must be a positive integer")
    if not isinstance(target_rate, int) or isinstance(target_rate, bool) or target_rate <= 0:
        raise RenderValidationError("Project sample rate must be a positive integer")
    array = np.asarray(samples)
    if array.ndim != 2 or array.shape[1] not in (1, 2) or array.shape[0] <= 0:
        raise RenderValidationError("Decoded audio must have non-empty mono or stereo frames")
    if not np.isfinite(array).all():
        raise RenderValidationError("Decoded audio must contain only finite samples")
    source = np.asarray(array, dtype=np.float32, order="C")
    if source_rate == target_rate:
        return np.array(source, dtype=np.float32, order="C", copy=True)

    output_frames = (source.shape[0] * target_rate + source_rate - 1) // source_rate
    positions = np.arange(output_frames, dtype=np.float64) * source_rate / target_rate
    last_index = source.shape[0] - 1
    positions = np.minimum(positions, last_index)
    left = np.floor(positions).astype(np.intp)
    right = np.minimum(left + 1, last_index)
    fraction = positions - left
    source_float64 = source.astype(np.float64)
    output = source_float64[left] * (1.0 - fraction[:, None]) + source_float64[right] * fraction[
        :, None
    ]
    return np.asarray(output, dtype=np.float32, order="C")


def resample_hq(
    samples: np.ndarray,
    source_rate: int,
    target_rate: int,
) -> np.ndarray:
    """Apply VibeSound's anti-aliased SoXR HQ sample-rate conversion policy."""

    array = np.asarray(samples)
    if array.ndim != 2 or array.shape[1] not in (1, 2) or array.shape[0] <= 0:
        raise RenderValidationError("Decoded audio must have non-empty mono or stereo frames")
    if source_rate <= 0 or target_rate <= 0:
        raise RenderValidationError("Audio sample rates must be positive")
    source = np.asarray(array, dtype=np.float32, order="C")
    if source_rate == target_rate:
        return np.array(source, dtype=np.float32, order="C", copy=True)
    try:
        output = soxr.resample(source, source_rate, target_rate, quality="HQ")
    except (TypeError, ValueError, RuntimeError) as error:
        raise RenderValidationError("SoXR could not resample the audio source") from error
    return np.asarray(output, dtype=np.float32, order="C")


def prepare_archive_project(path: Path | str, project: Project) -> PreparedRenderProject:
    """Decode every referenced archive asset and build a render-time snapshot."""

    return _prepare_archive_project(path, project, preserve_quantization=False)


def prepare_archive_playback_project(
    path: Path | str,
    project: Project,
) -> PreparedRenderProject:
    """Decode archive assets while preserving live transport quantization."""

    return _prepare_archive_project(path, project, preserve_quantization=True)


def prepare_working_project(snapshot: RepositorySnapshot) -> PreparedRenderProject:
    """Prepare a repository snapshot through its immutable on-disk audio cache."""

    return _prepare_working_project(snapshot, preserve_quantization=False)


def prepare_working_playback_project(
    snapshot: RepositorySnapshot,
) -> PreparedRenderProject:
    """Prepare cached working assets while retaining live quantization."""

    return _prepare_working_project(snapshot, preserve_quantization=True)


def _prepare_working_project(
    snapshot: RepositorySnapshot,
    *,
    preserve_quantization: bool,
) -> PreparedRenderProject:
    project = snapshot.project
    referenced_ids = {clip.asset_id for clip in project.clips}
    assets = {asset.id: asset for asset in project.assets}
    cache_root = snapshot.working_path / ".vibesound" / "cache" / "audio"
    cache_root.mkdir(parents=True, exist_ok=True)
    prepared: dict[UUID, _PreparedAsset] = {}
    for asset_id in sorted(referenced_ids, key=str):
        asset = assets[asset_id]
        cache_name = f"{asset.sha256}-{project.transport.sample_rate}-soxr-hq-v1.npy"
        cache_path = cache_root / cache_name
        if not cache_path.is_file():
            samples = _decode_path_asset(asset, snapshot.asset_paths[asset_id])
            output = resample_hq(samples, asset.sample_rate, project.transport.sample_rate)
            _write_array_cache(cache_path, output)
        try:
            mapped = np.load(cache_path, mmap_mode="r", allow_pickle=False)
            buffer = AudioBuffer.from_prevalidated(project.transport.sample_rate, mapped)
        except (OSError, ValueError) as error:
            cache_path.unlink(missing_ok=True)
            raise RenderValidationError(f"Audio cache is invalid for asset {asset.id}") from error
        prepared[asset_id] = _PreparedAsset(buffer=buffer, source_rate=asset.sample_rate)
    runtime_project = _runtime_project(
        project,
        prepared,
        preserve_quantization=preserve_quantization,
    )
    return PreparedRenderProject(
        runtime_project,
        InMemoryClipSourceProvider(
            {asset_id: item.buffer for asset_id, item in prepared.items()}
        ),
    )


def _prepare_archive_project(
    path: Path | str,
    project: Project,
    *,
    preserve_quantization: bool,
) -> PreparedRenderProject:
    """Build a project/source pair for rendering or real-time playback."""

    project_path = Path(path)
    referenced_ids = {clip.asset_id for clip in project.clips}
    assets = {asset.id: asset for asset in project.assets}
    payloads: dict[UUID, bytes] = {}
    try:
        with ZipFile(project_path, mode="r") as archive:
            for asset_id in sorted(referenced_ids, key=str):
                asset = assets[asset_id]
                payloads[asset_id] = archive.read(asset.member_path)
    except (BadZipFile, KeyError, OSError) as exc:
        raise RenderValidationError(f"Could not read referenced audio from {project_path}") from exc

    prepared: dict[UUID, _PreparedAsset] = {}
    for asset_id in sorted(referenced_ids, key=str):
        asset = assets[asset_id]
        prepared[asset_id] = _prepare_asset(
            asset,
            payloads[asset_id],
            project.transport.sample_rate,
        )

    runtime_project = _runtime_project(
        project,
        prepared,
        preserve_quantization=preserve_quantization,
    )
    provider = InMemoryClipSourceProvider(
        {asset_id: item.buffer for asset_id, item in prepared.items()}
    )
    return PreparedRenderProject(runtime_project, provider)


def prepare_source_provider(project: Project, sources: ClipSourceProvider) -> PreparedRenderProject:
    """Validate and prepare an injected source provider for project-rate rendering."""

    referenced_ids = {clip.asset_id for clip in project.clips}
    assets = {asset.id: asset for asset in project.assets}
    prepared: dict[UUID, _PreparedAsset] = {}
    for asset_id in sorted(referenced_ids, key=str):
        asset = assets[asset_id]
        try:
            source = sources.get(asset_id)
        except Exception as exc:
            raise RenderValidationError(
                f"Could not load audio source for asset {asset_id}"
            ) from exc
        if not isinstance(source, AudioBuffer):
            raise RenderValidationError(
                f"Audio source provider returned an invalid value for asset {asset_id}"
            )
        if source.sample_rate != asset.sample_rate:
            raise RenderValidationError(
                f"Audio source {asset_id} sample rate does not match the manifest"
            )
        if source.samples.shape[0] != asset.frames:
            raise RenderValidationError(
                f"Audio source {asset_id} frame count does not match the manifest"
            )
        if source.samples.shape[1] != asset.channels:
            raise RenderValidationError(
                f"Audio source {asset_id} channel count does not match the manifest"
            )
        output = resample_hq(
            source.samples,
            source.sample_rate,
            project.transport.sample_rate,
        )
        prepared[asset_id] = _PreparedAsset(
            buffer=AudioBuffer(project.transport.sample_rate, output),
            source_rate=source.sample_rate,
        )

    runtime_project = _runtime_project(project, prepared)
    provider = InMemoryClipSourceProvider(
        {asset_id: item.buffer for asset_id, item in prepared.items()}
    )
    return PreparedRenderProject(runtime_project, provider)


def _prepare_asset(asset: AssetReference, payload: bytes, target_rate: int) -> _PreparedAsset:
    actual_size = len(payload)
    actual_hash = hashlib.sha256(payload).hexdigest()
    if actual_size != asset.size_bytes:
        raise RenderValidationError(
            f"Asset {asset.id} size mismatch: manifest declares {asset.size_bytes}, "
            f"archive contains {actual_size} bytes"
        )
    if actual_hash != asset.sha256:
        raise RenderValidationError(f"Asset {asset.id} SHA-256 does not match the manifest")

    try:
        with sf.SoundFile(io.BytesIO(payload), mode="r") as audio:
            sample_rate = audio.samplerate
            channels = audio.channels
            frames = audio.frames
            audio_format = audio.format
            samples = audio.read(dtype="float32", always_2d=True)
    except (OSError, RuntimeError, ValueError) as exc:
        raise RenderValidationError(
            f"Asset {asset.id} is not a supported decodable audio file"
        ) from exc

    if sample_rate != asset.sample_rate:
        raise RenderValidationError(
            f"Asset {asset.id} sample rate mismatch: manifest declares {asset.sample_rate}, "
            f"decoded audio reports {sample_rate}"
        )
    if channels != asset.channels:
        raise RenderValidationError(
            f"Asset {asset.id} channel mismatch: manifest declares {asset.channels}, "
            f"decoded audio reports {channels}"
        )
    if frames != asset.frames or samples.shape[0] != asset.frames:
        raise RenderValidationError(
            f"Asset {asset.id} frame mismatch: manifest declares {asset.frames}, "
            f"decoded audio reports {frames}"
        )
    if str(audio_format).upper() != asset.format.upper():
        raise RenderValidationError(
            f"Asset {asset.id} format mismatch: manifest declares {asset.format}, "
            f"decoded audio reports {audio_format}"
        )
    if channels not in (1, 2):
        raise RenderValidationError(f"Asset {asset.id} has unsupported channel count {channels}")

    try:
        output = resample_hq(samples, sample_rate, target_rate)
        buffer = AudioBuffer(target_rate, output)
    except (RenderValidationError, ValueError) as exc:
        raise RenderValidationError(f"Asset {asset.id} cannot be prepared for rendering") from exc
    return _PreparedAsset(buffer=buffer, source_rate=sample_rate)


def _decode_path_asset(asset: AssetReference, path: Path) -> np.ndarray:
    if not path.is_file() or path.stat().st_size != asset.size_bytes:
        raise RenderValidationError(f"Asset {asset.id} file size does not match the manifest")
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
        if digest.hexdigest() != asset.sha256:
            raise RenderValidationError(f"Asset {asset.id} SHA-256 does not match the manifest")
        with sf.SoundFile(path, mode="r") as audio:
            if (
                audio.samplerate != asset.sample_rate
                or audio.channels != asset.channels
                or audio.frames != asset.frames
                or str(audio.format).upper() != asset.format.upper()
            ):
                raise RenderValidationError(
                    f"Decoded metadata does not match the manifest for asset {asset.id}"
                )
            samples = audio.read(dtype="float32", always_2d=True)
    except RenderValidationError:
        raise
    except (OSError, RuntimeError, ValueError) as error:
        raise RenderValidationError(f"Asset {asset.id} is not decodable") from error
    if not np.isfinite(samples).all():
        raise RenderValidationError(f"Asset {asset.id} contains non-finite samples")
    return np.asarray(samples, dtype=np.float32, order="C")


def _write_array_cache(path: Path, samples: np.ndarray) -> None:
    handle, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    try:
        with os.fdopen(handle, "wb") as output:
            np.save(output, np.asarray(samples, dtype=np.float32, order="C"), allow_pickle=False)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.close(handle)
        except OSError:
            pass
        Path(temporary_name).unlink(missing_ok=True)
        raise


def _runtime_project(
    project: Project,
    prepared: dict[UUID, _PreparedAsset],
    *,
    preserve_quantization: bool = False,
) -> Project:
    """Convert persisted source-frame regions to the resampled runtime units."""

    target_rate = project.transport.sample_rate
    runtime = project.model_copy(deep=True)
    if not preserve_quantization:
        runtime.transport.quantization = "none"

    runtime_assets: list[AssetReference] = []
    for asset in runtime.assets:
        item = prepared.get(asset.id)
        if item is None:
            runtime_assets.append(asset)
            continue
        runtime_assets.append(
            asset.model_copy(
                update={
                    "sample_rate": target_rate,
                    "frames": item.buffer.samples.shape[0],
                }
            )
        )
    runtime.assets = runtime_assets

    runtime_clips = []
    for clip in runtime.clips:
        item = prepared.get(clip.asset_id)
        if item is None:
            runtime_clips.append(clip)
            continue
        source_rate = item.source_rate
        offset = (clip.source_offset_frames * target_rate) // source_rate
        duration = (
            None
            if clip.duration_frames is None
            else (clip.duration_frames * target_rate + source_rate - 1) // source_rate
        )
        runtime_clips.append(
            clip.model_copy(
                update={"source_offset_frames": offset, "duration_frames": duration}
            )
        )
    runtime.clips = runtime_clips
    return runtime
