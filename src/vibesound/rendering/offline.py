"""Deterministic archive and in-memory offline rendering."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from threading import Event

import soundfile as sf

from vibesound.engine import ClipSourceProvider, EngineError, SessionEngine
from vibesound.project import (
    ProjectArchiveError,
    load_project,
    validate_project,
)
from vibesound.project.models import Project
from vibesound.project.repository import RepositorySnapshot
from vibesound.project.validation import project_reference_issues
from vibesound.rendering.errors import (
    InvalidRenderRequestError,
    RenderCancelledError,
    RenderError,
    RenderOutputError,
    RenderValidationError,
)
from vibesound.rendering.sources import (
    prepare_archive_project,
    prepare_source_provider,
    prepare_working_project,
)
from vibesound.rendering.types import RenderCommand, RenderMetadata, RenderRequest

RENDER_BLOCK_FRAMES = 4096
ProgressCallback = Callable[[float], None]


def render(
    project: Project,
    sources: ClipSourceProvider,
    output_path: Path | str,
    request: RenderRequest,
) -> RenderMetadata:
    """Render an already-loaded project using an injected source provider."""

    _validate_project(project)
    output = _validate_output_path(output_path)
    total_frames = _validate_request(project, request)
    try:
        prepared = prepare_source_provider(project, sources)
    except RenderError:
        raise
    except Exception as exc:  # pragma: no cover - defensive provider boundary
        raise RenderValidationError("Could not prepare injected project audio") from exc
    return _render_prepared(
        project,
        prepared.project,
        prepared.sources,
        output,
        total_frames,
        request,
    )


def render_project(
    project_path: Path | str,
    output_path: Path | str,
    request: RenderRequest,
) -> RenderMetadata:
    """Validate, decode, and render a self-contained ``.vibesound`` archive."""

    project_file = Path(project_path)
    output = _validate_output_path(output_path)
    if _same_path(project_file, output):
        raise RenderValidationError("Render output must not overwrite the source project archive")

    report = validate_project(project_file)
    if not report.ok:
        details = "; ".join(f"{issue.path}: {issue.message}" for issue in report.issues)
        raise RenderValidationError(f"Project archive validation failed: {details}")
    try:
        project = load_project(project_file)
    except ProjectArchiveError as exc:
        raise RenderValidationError(f"Could not load project archive: {project_file}") from exc

    _validate_project(project)
    total_frames = _validate_request(project, request)
    try:
        prepared = prepare_archive_project(project_file, project)
    except RenderError:
        raise
    except Exception as exc:  # pragma: no cover - defensive boundary for archive providers
        raise RenderValidationError(f"Could not prepare project audio: {project_file}") from exc
    return _render_prepared(
        project,
        prepared.project,
        prepared.sources,
        output,
        total_frames,
        request,
    )


def render_snapshot(
    snapshot: RepositorySnapshot,
    output_path: Path | str,
    request: RenderRequest,
    *,
    cancel_event: Event | None = None,
    progress: ProgressCallback | None = None,
) -> RenderMetadata:
    """Render an immutable working-project snapshot with job control hooks."""

    project = snapshot.project
    _validate_project(project)
    output = _validate_output_path(output_path)
    total_frames = _validate_request(project, request)
    prepared = prepare_working_project(snapshot)
    return _render_prepared(
        project,
        prepared.project,
        prepared.sources,
        output,
        total_frames,
        request,
        cancel_event=cancel_event,
        progress=progress,
    )


def _validate_project(project: Project) -> None:
    if not isinstance(project, Project):
        raise RenderValidationError("render() requires a Project instance")
    issues = project_reference_issues(project)
    if issues:
        details = "; ".join(f"{issue.path}: {issue.message}" for issue in issues)
        raise RenderValidationError(f"Project validation failed: {details}")


def _validate_request(project: Project, request: RenderRequest) -> int:
    if not isinstance(request, RenderRequest):
        raise InvalidRenderRequestError("render() requires a RenderRequest instance")
    try:
        total_frames = request.total_frames(project)
    except (InvalidRenderRequestError, ValueError) as exc:
        if isinstance(exc, InvalidRenderRequestError):
            raise
        raise InvalidRenderRequestError("Could not convert render duration to frames") from exc
    track_ids = {track.id for track in project.tracks}
    scene_ids = {scene.id for scene in project.scenes}
    for command in request.commands:
        if command.frame > total_frames:
            raise InvalidRenderRequestError(
                f"Render command at frame {command.frame} is beyond the output end frame "
                f"{total_frames}"
            )
        if command.operation in ("launch_slot", "stop_track") and command.track_id not in track_ids:
            raise InvalidRenderRequestError(f"Unknown track in render command: {command.track_id}")
        if (
            command.operation in ("launch_slot", "launch_scene")
            and command.scene_id not in scene_ids
        ):
            raise InvalidRenderRequestError(f"Unknown scene in render command: {command.scene_id}")
    return total_frames


def _validate_output_path(output_path: Path | str) -> Path:
    try:
        output = Path(output_path)
    except TypeError as exc:
        raise RenderOutputError("Render output path must be path-like") from exc
    if output.exists() and output.is_dir():
        raise RenderOutputError(f"Render output path is a directory: {output}")
    if output.parent.exists() and not output.parent.is_dir():
        raise RenderOutputError(f"Render output parent is not a directory: {output.parent}")
    return output


def _same_path(first: Path, second: Path) -> bool:
    try:
        return first.resolve(strict=False) == second.resolve(strict=False)
    except OSError:
        return os.path.normcase(os.path.abspath(first)) == os.path.normcase(os.path.abspath(second))


def _render_prepared(
    project: Project,
    runtime_project: Project,
    sources: ClipSourceProvider,
    output: Path,
    total_frames: int,
    request: RenderRequest,
    *,
    cancel_event: Event | None = None,
    progress: ProgressCallback | None = None,
) -> RenderMetadata:
    try:
        engine = SessionEngine(runtime_project, sources)
    except EngineError as exc:
        raise RenderValidationError(f"Project sources cannot be rendered: {exc}") from exc
    return _write_atomic(
        project,
        engine,
        output,
        total_frames,
        request,
        cancel_event=cancel_event,
        progress=progress,
    )


def _write_atomic(
    project: Project,
    engine: SessionEngine,
    output: Path,
    total_frames: int,
    request: RenderRequest,
    *,
    cancel_event: Event | None = None,
    progress: ProgressCallback | None = None,
) -> RenderMetadata:
    temporary_path: Path | None = None
    current_frame = 0
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{output.name}.", suffix=".tmp", dir=output.parent
        )
        os.close(fd)
        temporary_path = Path(temporary_name)
        with sf.SoundFile(
            temporary_path,
            mode="w",
            samplerate=project.transport.sample_rate,
            channels=2,
            format="WAV",
            subtype="FLOAT",
        ) as audio_file:
            engine.play()

            def write_until(target_frame: int) -> None:
                nonlocal current_frame
                while current_frame < target_frame:
                    if cancel_event is not None and cancel_event.is_set():
                        raise RenderCancelledError("Render job was cancelled")
                    block_frames = min(RENDER_BLOCK_FRAMES, target_frame - current_frame)
                    step = engine.advance(block_frames)
                    audio_file.write(step.samples)
                    current_frame += block_frames
                    if progress is not None:
                        progress(current_frame / total_frames)

            for command in request.commands:
                write_until(command.frame)
                _dispatch(engine, command)
                engine.advance(0)
            write_until(total_frames)

        _normalize_wav_metadata(temporary_path)
        if progress is not None:
            progress(1.0)

        with temporary_path.open("r+b") as temporary_file:
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, output)
        temporary_path = None
    except RenderError:
        raise
    except EngineError as exc:
        raise RenderValidationError(f"Render engine failed: {exc}") from exc
    except (OSError, RuntimeError, ValueError) as exc:
        raise RenderOutputError(f"Could not write render output: {output}") from exc
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

    return RenderMetadata(
        project_id=project.project_id,
        revision=project.revision.number,
        output_path=output,
        format="WAV",
        subtype="FLOAT",
        sample_rate=project.transport.sample_rate,
        channels=2,
        frames=total_frames,
        duration_seconds=total_frames / project.transport.sample_rate,
    )


def _normalize_wav_metadata(path: Path) -> None:
    """Zero libsndfile's wall-clock PEAK timestamp so FLOAT WAV bytes are reproducible."""

    with path.open("r+b") as stream:
        header = stream.read(12)
        if len(header) != 12 or header[:4] != b"RIFF" or header[8:] != b"WAVE":
            raise RenderOutputError("Rendered output is not a RIFF/WAVE file")
        while True:
            chunk_header = stream.read(8)
            if not chunk_header:
                return
            if len(chunk_header) != 8:
                raise RenderOutputError("Rendered WAV contains a truncated chunk header")
            chunk_id = chunk_header[:4]
            chunk_size = int.from_bytes(chunk_header[4:], "little")
            payload_start = stream.tell()
            if chunk_id == b"PEAK":
                if chunk_size < 8:
                    raise RenderOutputError("Rendered WAV contains an invalid PEAK chunk")
                stream.seek(payload_start + 4)
                stream.write(b"\0\0\0\0")
                return
            stream.seek(payload_start + chunk_size + (chunk_size & 1))


def _dispatch(engine: SessionEngine, command: RenderCommand) -> None:
    if command.operation == "launch_slot":
        assert command.track_id is not None and command.scene_id is not None
        engine.launch_slot(command.track_id, command.scene_id)
    elif command.operation == "launch_scene":
        assert command.scene_id is not None
        engine.launch_scene(command.scene_id)
    elif command.operation == "stop_track":
        assert command.track_id is not None
        engine.stop_track(command.track_id)
    else:
        engine.stop_all()
