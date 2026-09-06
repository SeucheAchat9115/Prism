"""Deterministic offline rendering for script-authored Prism projects."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import tempfile
import uuid
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Literal, Mapping

import numpy as np
import soundfile as sf
import soxr

from prism.arrangement import compile_track_events
from prism.effects import (
    has_automation,
    parameter_values,
    process_effect_chain,
    process_track_plugins,
)
from prism.errors import ProjectError, RenderError
from prism.music import Note, db_gain
from prism.project.builder import (
    AudioClip,
    AudioReleasePolicy,
    DrumClip,
    MidiClip,
    Project,
    SampleClip,
    Track,
    TrackClip,
)
from prism.synthesis.engine import render_native_synth
from prism.synthesis.types import NativeSynthSpec

OutputChannels = Literal["mono", "stereo"]
BitDepth = Literal[16, 24, 32]


@dataclass(frozen=True, slots=True)
class RenderResult:
    """Useful facts about one completed WAV render."""

    path: Path
    sample_rate: int
    channels: int
    frames: int
    duration_seconds: float
    sha256: str
    peak_dbfs: float | None
    bit_depth: BitDepth
    tail_seconds: float

    def __str__(self) -> str:
        return f"Rendered {self.duration_seconds:.2f}s to {self.path}"


@dataclass(frozen=True, slots=True)
class StemFile:
    """One WAV file created by :meth:`prism.Project.render_stems`."""

    name: str
    kind: Literal["track", "bus", "master"]
    path: Path
    sha256: str
    peak_dbfs: float | None


@dataclass(frozen=True, slots=True)
class StemRenderResult:
    """The aligned files and audio format returned by a stem render."""

    directory: Path
    sample_rate: int
    channels: int
    frames: int
    duration_seconds: float
    bit_depth: BitDepth
    tail_seconds: float
    tracks: tuple[StemFile, ...]
    buses: tuple[StemFile, ...]
    master: StemFile
    generation: int = 0

    @property
    def files(self) -> tuple[StemFile, ...]:
        """Return every track, bus, and master file in render order."""

        return (*self.tracks, *self.buses, self.master)

    def __str__(self) -> str:
        count = len(self.tracks) + len(self.buses) + 1
        return (
            f"Rendered {count} aligned stem files to generation {self.generation} "
            f"at {self.directory}"
        )


@dataclass(frozen=True, slots=True)
class _RenderedProject:
    frames: int
    tracks: dict[str, np.ndarray]
    buses: dict[str, np.ndarray]
    master: np.ndarray


@dataclass(frozen=True, slots=True)
class _ExportSettings:
    bit_depth: BitDepth
    channels: OutputChannels
    sample_rate: int
    tail_seconds: float


@dataclass(frozen=True, slots=True)
class _StemManifest:
    """The last successfully published stem generation and its file ownership."""

    generation: int
    directory: Path
    files: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class _ScheduledVoice:
    """One non-MIDI source voice placed on the absolute render timeline.

    The schedule deliberately contains prepared source data and resolved frame
    endpoints.  Track rendering consumes this data without walking sections or
    interpreting ``loop``/``repeat`` again, leaving one reusable boundary for a
    future block renderer.
    """

    start_frame: int
    end_frame: int
    source: np.ndarray
    loop: bool
    gain_db: float
    fade_out_frames: int
    release_policy: AudioReleasePolicy
    order: int


_STEM_MANIFEST_SCHEMA_VERSION = 1
_STEM_METADATA_DIRECTORY = ".prism-stems"
_STEM_MANIFEST_FILENAME = "manifest.json"


def render_project(
    project: Project,
    output: str | Path,
    *,
    bit_depth: BitDepth = 16,
    channels: OutputChannels = "stereo",
    sample_rate: int | None = None,
    tail_seconds: float = 0.0,
) -> RenderResult:
    """Render every named section in order to a WAV file."""

    try:
        output_path = project._output_path(output, suffix=".wav")
        settings = _export_settings(
            project,
            bit_depth=bit_depth,
            channels=channels,
            sample_rate=sample_rate,
            tail_seconds=tail_seconds,
        )
        rendered = _render_buffers(project, tail_seconds=settings.tail_seconds)
        output_samples = _prepare_export(rendered.master, project.sample_rate, settings)
        _write_wav(
            output_path,
            output_samples,
            settings.sample_rate,
            bit_depth=settings.bit_depth,
        )
        return RenderResult(
            path=output_path,
            sample_rate=settings.sample_rate,
            channels=output_samples.shape[1],
            frames=output_samples.shape[0],
            duration_seconds=output_samples.shape[0] / settings.sample_rate,
            sha256=_sha256(output_path),
            peak_dbfs=_peak_dbfs(output_samples),
            bit_depth=settings.bit_depth,
            tail_seconds=settings.tail_seconds,
        )
    except (ProjectError, RenderError):
        raise
    except (OSError, RuntimeError, ValueError) as error:
        raise RenderError(f"Could not render {project.name!r}: {error}") from error


def render_stems(
    project: Project,
    output: str | Path,
    *,
    bit_depth: BitDepth = 16,
    channels: OutputChannels = "stereo",
    sample_rate: int | None = None,
    tail_seconds: float = 0.0,
) -> StemRenderResult:
    """Render aligned track, bus/return, and master WAV files.

    The requested folder is a container for versioned generations. A generation
    is written privately first; its ownership manifest becomes current only after
    every WAV is complete. ``StemRenderResult.directory`` is therefore the
    recoverable, completed generation rather than the container itself.
    """

    directory = project._output_directory(output)
    settings = _export_settings(
        project,
        bit_depth=bit_depth,
        channels=channels,
        sample_rate=sample_rate,
        tail_seconds=tail_seconds,
    )
    previous: _StemManifest | None = None
    staging: Path | None = None
    staging_created = False
    try:
        protected = project._protected_project_files()
        _validate_stem_output(project, directory, protected)
        previous = _read_stem_manifest(project, directory, protected)
        rendered = _render_buffers(project, tail_seconds=settings.tail_seconds)

        metadata = directory / _STEM_METADATA_DIRECTORY
        generations = metadata / "generations"
        _make_directory(metadata, project, protected, "Stem metadata directory")
        _make_directory(generations, project, protected, "Stem generations directory")

        generation_number = 1 if previous is None else previous.generation + 1
        generation_name = f"generation-{generation_number:06d}-{uuid.uuid4().hex[:12]}"
        generation = generations / generation_name
        staging = generations / f".staging-{uuid.uuid4().hex}"
        _assert_safe_managed_path(project, generation, protected, "Stem generation")
        _assert_safe_managed_path(project, staging, protected, "Stem staging directory")
        staging.mkdir()
        staging_created = True

        track_files = tuple(
            _write_stem(
                _safe_stem_destination(
                    project,
                    staging / "tracks" / _stem_filename(index, name),
                    protected,
                ),
                _prepare_export(rendered.tracks[name], project.sample_rate, settings),
                settings,
                name=name,
                kind="track",
            )
            for index, name in enumerate(rendered.tracks, start=1)
        )
        bus_files = tuple(
            _write_stem(
                _safe_stem_destination(
                    project,
                    staging / "buses" / _stem_filename(index, name),
                    protected,
                ),
                _prepare_export(rendered.buses[name], project.sample_rate, settings),
                settings,
                name=name,
                kind="bus",
            )
            for index, name in enumerate(rendered.buses, start=1)
        )
        master_samples = _prepare_export(rendered.master, project.sample_rate, settings)
        master = _write_stem(
            _safe_stem_destination(project, staging / "master.wav", protected),
            master_samples,
            settings,
            name="Master",
            kind="master",
        )
        staged_files = (*track_files, *bus_files, master)
        manifest = _StemManifest(
            generation=generation_number,
            directory=generation,
            files=tuple(
                (
                    item.path.relative_to(staging).as_posix(),
                    item.sha256,
                )
                for item in staged_files
            ),
        )
        staging_root = staging
        os.replace(staging, generation)
        staging = None
        staging_created = False
        _publish_stem_manifest(project, directory, protected, manifest)

        if previous is not None:
            _remove_stale_stems(
                previous.directory,
                set(),
                ownership=dict(previous.files),
                project=project,
                protected=protected,
            )

        track_files = tuple(_relocate_stem(item, staging_root, generation) for item in track_files)
        bus_files = tuple(_relocate_stem(item, staging_root, generation) for item in bus_files)
        master = _relocate_stem(master, staging_root, generation)
        return StemRenderResult(
            directory=generation,
            sample_rate=settings.sample_rate,
            channels=1 if settings.channels == "mono" else 2,
            frames=master_samples.shape[0],
            duration_seconds=master_samples.shape[0] / settings.sample_rate,
            bit_depth=settings.bit_depth,
            tail_seconds=settings.tail_seconds,
            tracks=track_files,
            buses=bus_files,
            master=master,
            generation=generation_number,
        )
    except ProjectError:
        raise
    except RenderError as error:
        if previous is None:
            raise
        raise RenderError(
            f"{error} Previous completed generation remains at {previous.directory}."
        ) from error
    except (OSError, RuntimeError, ValueError) as error:
        previous_path = "none"
        if previous is not None:
            previous_path = str(previous.directory)
        raise RenderError(
            f"Could not render stems for {project.name!r}: {error}. "
            f"Previous completed generation remains at {previous_path}."
        ) from error
    finally:
        if staging_created and staging is not None and staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


def _render_buffers(project: Project, *, tail_seconds: float = 0.0) -> _RenderedProject:
    summary = project.validate()
    timing = project.timing
    song_frames = timing.bar_to_frame(summary.bars)
    tail_frames = timing.seconds_to_frames(tail_seconds)
    total_frames = song_frames + tail_frames
    mix = np.zeros((total_frames, 2), dtype=np.float64)
    track_outputs: dict[str, np.ndarray] = {}
    for track in project.tracks:
        if track.muted:
            track_outputs[track.name] = np.zeros_like(mix)
            continue
        if isinstance(track.clip, MidiClip):
            arranged = _arrange_midi_track(project, track, total_frames, summary.bars)
        else:
            schedule = _schedule_audio_voices(project, track, total_frames)
            arranged = _render_voice_schedule(schedule, total_frames)
        processed = process_track_plugins(project, track, arranged)
        track_outputs[track.name] = _mix_channel(
            processed, gain_db=track.gain_db, pan=track.pan
        )

    bus_inputs = {bus.name: np.zeros_like(mix) for bus in project.buses}
    for track in project.tracks:
        track_output = track_outputs[track.name]
        if track.output_bus is None:
            mix += track_output
        else:
            bus_inputs[track.output_bus.name] += track_output
        for send in track.sends:
            bus_inputs[send.bus] += track_output * db_gain(send.gain_db)

    bus_outputs: dict[str, np.ndarray] = {}
    for bus in project.buses:
        if bus.muted:
            bus_outputs[bus.name] = np.zeros_like(mix)
            continue
        processed = process_effect_chain(project, bus.effects, bus_inputs[bus.name])
        bus_output = _mix_channel(processed, gain_db=bus.gain_db, pan=bus.pan)
        bus_outputs[bus.name] = bus_output
        mix += bus_output

    mix = process_effect_chain(project, project.master_effects, mix)
    mix *= db_gain(project.master_gain_db)
    peak = float(np.max(np.abs(mix))) if mix.size else 0.0
    target = 10.0 ** (-1.0 / 20.0)
    if project.normalize and peak > target:
        mix *= target / peak
    return _RenderedProject(
        frames=total_frames,
        tracks=track_outputs,
        buses=bus_outputs,
        master=mix,
    )


def _schedule_audio_voices(
    project: Project,
    track: Track,
    total_frames: int,
) -> tuple[_ScheduledVoice, ...]:
    """Resolve sample, audio, and drum placements into absolute source voices.

    ``AudioClip.loop`` repeats its prepared source only inside one placement.
    ``ClipPlacement.repeat`` creates another placement in the active section.
    Natural one-shot/sample/percussion voices can outlive either boundary and
    are clipped only by the requested output duration.  ``cut`` and ``legacy``
    use the owning placement/section boundary; ``choke`` additionally ends a
    prior voice when a later voice on this track starts.
    """

    timing = project.timing
    prepared: dict[int, np.ndarray] = {}
    voices: list[_ScheduledVoice] = []
    order = 0
    cursor_bar = 0.0

    for section in project.sections:
        section_end = timing.bar_to_frame(cursor_bar + section.bars)
        active = section.tracks is None or track.name in section.tracks
        if active:
            for placement in track.clips_for(section):
                clip = placement.clip
                if isinstance(clip, MidiClip):
                    continue
                clip_frames = timing.bars_to_frames(clip.bars)
                placement_start = timing.bar_to_frame(
                    cursor_bar + placement.start_bar
                )
                available = section_end - placement_start
                if available <= 0:
                    continue
                repeats = (
                    max(1, math.ceil(available / clip_frames))
                    if placement.repeat
                    else 1
                )
                source = None
                if isinstance(clip, SampleClip | AudioClip):
                    source = prepared.get(id(clip))
                    if source is None:
                        source = _prepare_audio(project, clip)
                        prepared[id(clip)] = source

                for repeat_index in range(repeats):
                    occurrence_start = placement_start + repeat_index * clip_frames
                    if occurrence_start >= section_end or occurrence_start >= total_frames:
                        continue
                    occurrence_end = min(
                        section_end,
                        occurrence_start + clip_frames,
                        total_frames,
                    )
                    if occurrence_end <= occurrence_start:
                        continue
                    release_policy = (
                        clip.release_policy or project.audio_release_policy
                    )
                    if isinstance(clip, SampleClip):
                        assert source is not None
                        boundaries = np.rint(
                            np.linspace(0, clip_frames, len(clip.pattern) + 1)
                        ).astype(np.int64)
                        for step_index, step in enumerate(clip.pattern):
                            if step == "-":
                                continue
                            voice_start = occurrence_start + int(boundaries[step_index])
                            if voice_start >= occurrence_end:
                                continue
                            _append_scheduled_voice(
                                voices,
                                source=source,
                                start_frame=voice_start,
                                natural_end=voice_start + source.shape[0],
                                boundary_end=occurrence_end,
                                total_frames=total_frames,
                                loop=False,
                                gain_db=clip.gain_db,
                                fade_out_frames=_fade_out_frames(
                                    clip.fade_out_ms, project.sample_rate
                                ),
                                release_policy=release_policy,
                                order=order,
                            )
                            order += 1
                    elif isinstance(clip, AudioClip):
                        assert source is not None
                        _append_scheduled_voice(
                            voices,
                            source=source,
                            start_frame=occurrence_start,
                            natural_end=(
                                occurrence_end
                                if clip.loop
                                else occurrence_start + source.shape[0]
                            ),
                            boundary_end=occurrence_end,
                            total_frames=total_frames,
                            loop=clip.loop,
                            gain_db=clip.gain_db,
                            fade_out_frames=_fade_out_frames(
                                clip.fade_out_ms, project.sample_rate
                            ),
                            release_policy=release_policy,
                            order=order,
                        )
                        order += 1
                    else:
                        assert isinstance(clip, DrumClip)
                        boundaries = np.rint(
                            np.linspace(0, clip_frames, len(clip.pattern) + 1)
                        ).astype(np.int64)
                        for step_index, step in enumerate(clip.pattern):
                            if step == "-":
                                continue
                            voice_start = occurrence_start + int(boundaries[step_index])
                            if voice_start >= occurrence_end:
                                continue
                            hit = _drum_hit_source(
                                project,
                                clip,
                                step,
                                seed=(
                                    clip.seed
                                    + 1_000_003 * repeat_index
                                    + step_index
                                )
                                % 4_294_967_296,
                            )
                            boundary_end = (
                                occurrence_start + int(boundaries[step_index + 1])
                                if release_policy == "legacy"
                                else occurrence_end
                            )
                            _append_scheduled_voice(
                                voices,
                                source=hit,
                                start_frame=voice_start,
                                natural_end=voice_start + hit.shape[0],
                                boundary_end=boundary_end,
                                total_frames=total_frames,
                                loop=False,
                                gain_db=0.0,
                                fade_out_frames=0,
                                release_policy=release_policy,
                                order=order,
                            )
                            order += 1
        cursor_bar += section.bars

    return _apply_choke_policy(tuple(voices))


def _append_scheduled_voice(
    voices: list[_ScheduledVoice],
    *,
    source: np.ndarray,
    start_frame: int,
    natural_end: int,
    boundary_end: int,
    total_frames: int,
    loop: bool,
    gain_db: float,
    fade_out_frames: int,
    release_policy: AudioReleasePolicy,
    order: int,
) -> None:
    end_frame = natural_end
    if release_policy in {"cut", "legacy"}:
        end_frame = min(end_frame, boundary_end)
    end_frame = min(end_frame, total_frames)
    if end_frame <= start_frame:
        return
    voices.append(
        _ScheduledVoice(
            start_frame=start_frame,
            end_frame=end_frame,
            source=source,
            loop=loop,
            gain_db=gain_db,
            fade_out_frames=fade_out_frames,
            release_policy=release_policy,
            order=order,
        )
    )


def _apply_choke_policy(
    voices: tuple[_ScheduledVoice, ...],
) -> tuple[_ScheduledVoice, ...]:
    """End choke-mode voices at the next trigger on their track."""

    ordered = tuple(sorted(voices, key=lambda voice: (voice.start_frame, voice.order)))
    future_starts = sorted({voice.start_frame for voice in ordered})
    next_start: dict[int, int | None] = {
        start: future_starts[index + 1] if index + 1 < len(future_starts) else None
        for index, start in enumerate(future_starts)
    }
    result: list[_ScheduledVoice] = []
    for voice in ordered:
        if voice.release_policy != "choke":
            result.append(voice)
            continue
        next_trigger = next_start[voice.start_frame]
        if next_trigger is None:
            result.append(voice)
            continue
        result.append(replace(voice, end_frame=min(voice.end_frame, next_trigger)))
    return tuple(voice for voice in result if voice.end_frame > voice.start_frame)


def _render_voice_schedule(
    voices: tuple[_ScheduledVoice, ...],
    total_frames: int,
) -> np.ndarray:
    """Render a resolved voice schedule before track effects and mixing."""

    arranged = np.zeros((total_frames, 2), dtype=np.float64)
    for voice in voices:
        end_frame = min(voice.end_frame, total_frames)
        length = end_frame - voice.start_frame
        if length <= 0:
            continue
        placed = (
            _loop_to(voice.source, length)
            if voice.loop
            else _fit_to(voice.source, length)
        )
        if not math.isclose(voice.gain_db, 0.0, abs_tol=1e-12):
            placed *= db_gain(voice.gain_db)
        _apply_fade_out(placed, voice.fade_out_frames)
        arranged[voice.start_frame:end_frame] += placed
    return arranged


def _fade_out_frames(duration_ms: float, sample_rate: int) -> int:
    return max(0, int(round(duration_ms * sample_rate / 1_000.0)))


def _apply_fade_out(samples: np.ndarray, fade_frames: int) -> None:
    length = min(samples.shape[0], fade_frames)
    if length:
        samples[-length:] *= np.linspace(1.0, 0.0, length, endpoint=True)[:, np.newaxis]


_DRUM_RELEASE_SECONDS = {"kick": 0.42, "snare": 0.24, "hihat": 0.085}


def _drum_hit_source(
    project: Project,
    clip: DrumClip,
    token: str,
    *,
    seed: int,
) -> np.ndarray:
    """Render one percussion envelope without imposing a pattern-step choke."""

    duration = max(
        1,
        int(round(_DRUM_RELEASE_SECONDS.get(clip.preset, 0.085) * project.sample_rate)),
    )
    return _synth_audio(
        project,
        NativeSynthSpec(
            preset=clip.preset,
            sequence=(token,),
            bars=1,
            frame_count=duration,
            gain_db=clip.gain_db,
            seed=seed,
        ),
    )


def _clip_buffer(project: Project, track: Track, clip: TrackClip) -> np.ndarray:
    """Build one clip-local buffer for compatibility with older callers.

    The arrangement renderer no longer uses this helper: it uses
    ``_schedule_audio_voices`` so source voices can cross section boundaries.
    Keeping the helper makes the old clip-level shape useful to diagnostics and
    preserves a small, deterministic unit of source preparation.
    """

    timing = project.timing
    if isinstance(clip, SampleClip):
        source = _prepare_audio(project, clip)
        frames = timing.bars_to_frames(clip.bars)
        output = np.zeros((frames, 2), dtype=np.float64)
        boundaries = np.rint(np.linspace(0, frames, len(clip.pattern) + 1)).astype(np.int64)
        source = source * db_gain(clip.gain_db)
        for index, step in enumerate(clip.pattern):
            if step == "-":
                continue
            start = int(boundaries[index])
            length = min(source.shape[0], frames - start)
            placed = source[:length].copy()
            _apply_fade_out(placed, _fade_out_frames(clip.fade_out_ms, project.sample_rate))
            output[start : start + length] += placed
        return output
    if isinstance(clip, AudioClip):
        source = _prepare_audio(project, clip)
        frames = timing.bars_to_frames(clip.bars)
        output = _loop_to(source, frames) if clip.loop else _fit_to(source, frames)
        output *= db_gain(clip.gain_db)
        _apply_fade_out(output, _fade_out_frames(clip.fade_out_ms, project.sample_rate))
        return output
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
        note_events=clip.events,
        pitch_bend=clip.pitch_bend,
        modulation=clip.modulation,
        uniwave=clip.uniwave,
        bars=clip.bars,
        waveform=clip.waveform,
        attack_ms=clip.attack_ms,
        decay_ms=clip.decay_ms,
        sustain_level=clip.sustain,
        release_ms=clip.release_ms,
        cutoff_hz=(
            20_000.0
            if has_automation(project, track.instrument_plugin, "cutoff_hz")
            else clip.cutoff_hz
        ),
        gate=clip.gate,
        gain_db=clip.gain_db,
    )
    return _synth_audio(project, spec)


def _prepare_audio(project: Project, clip: SampleClip | AudioClip) -> np.ndarray:
    """Apply deterministic source selection and playback edits to an audio file."""

    source = _read_audio(project.root / clip.path, project.sample_rate)
    start = project.timing.seconds_to_frames(clip.start_seconds)
    end = (
        source.shape[0]
        if clip.end_seconds is None
        else project.timing.seconds_to_frames(clip.end_seconds)
    )
    if start >= source.shape[0]:
        raise RenderError(
            f"Audio start_seconds is outside source {clip.path!r} ({clip.start_seconds:g}s)."
        )
    source = source[start : min(end, source.shape[0])]
    if source.shape[0] == 0:
        raise RenderError(f"Audio source region is empty: {clip.path}")
    if clip.reverse:
        source = source[::-1].copy()
    speed = clip.playback_rate * 2.0 ** (clip.transpose_semitones / 12.0)
    if not math.isclose(speed, 1.0):
        source = _time_resize(source, max(1, int(round(source.shape[0] / speed))))
    if clip.stretch_bars is not None:
        target_frames = max(1, project.timing.bars_to_frames(clip.stretch_bars))
        source = _time_resize(source, target_frames)
    if clip.fade_in_ms > 0.0:
        fade_frames = min(
            source.shape[0], int(round(clip.fade_in_ms * project.sample_rate / 1_000.0))
        )
        if fade_frames:
            source[:fade_frames] *= np.linspace(
                0.0, 1.0, fade_frames, endpoint=True
            )[:, np.newaxis]
    # Fade-out is applied by the voice scheduler at the selected natural or
    # cut endpoint.  Applying it here would place the fade at the prepared
    # source endpoint even when a deliberate arrangement cut happens earlier.
    return np.asarray(source, dtype=np.float64)


def _time_resize(source: np.ndarray, frames: int) -> np.ndarray:
    """Resize audio with deterministic linear interpolation while preserving channels."""

    if source.shape[0] == frames:
        return np.asarray(source, dtype=np.float64)
    old_positions = np.linspace(0.0, 1.0, source.shape[0])
    new_positions = np.linspace(0.0, 1.0, frames)
    return np.column_stack(
        [
            np.interp(new_positions, old_positions, source[:, channel])
            for channel in range(source.shape[1])
        ]
    ).astype(np.float64)


def _arrange_midi_track(
    project: Project, track: Track, total_frames: int, total_bars: int
) -> np.ndarray:
    """Render one track from the same compiled stream used by MIDI export.

    Native instruments and VST3 instruments consume the complete stream in one
    pass.  A VST3 track is rendered by one isolated worker/plugin instance;
    clip gain is applied only once when every placement declares the same value.
    """

    stream = compile_track_events(
        project,
        track,
        total_bars=total_bars,
        total_frames=total_frames,
    )
    arranged = np.zeros((total_frames, 2), dtype=np.float64)
    clip = track.clip
    assert isinstance(clip, MidiClip)
    instrument = track.instrument_plugin
    if instrument is not None and instrument.vst3 is not None:
        from prism.vst_host import render_vst3_instrument

        if not stream.notes:
            return arranged
        rendered = render_vst3_instrument(project, instrument, stream, total_frames)
        arranged[:] = rendered
        return _apply_output_gain(
            project,
            track,
            arranged,
            base_gain_db=track._vst_clip_gain_db(),
        )

    automation = _synth_automation(project, track, total_frames)
    notes = tuple(
        Note(
            note.pitch,
            start=note.on_beat,
            duration=max(1e-12, note.off_beat - note.on_beat),
            velocity=note.velocity,
        )
        for note in stream.notes
        if note.pitch is not None
    )
    note_gains = tuple(note.gain_db for note in stream.notes if note.pitch is not None)
    if not notes:
        return arranged
    spec = NativeSynthSpec(
        preset=clip.instrument,
        sequence=clip.notes,
        note_events=notes,
        note_gains_db=note_gains,
        pitch_bend=stream.controller_points("pitch_bend"),
        modulation=stream.controller_points("modulation"),
        uniwave=clip.uniwave,
        automation=automation,
        automation_base_gain_db=_automation_base_gain(track) if automation else None,
        # ``bars`` remains the authored clip span for NativeSynthSpec.  The
        # absolute arrangement span is represented by the compiled note events
        # and this explicit frame range, so a 257-bar song is not mistaken for
        # a 257-bar authored clip.
        frame_count=total_frames,
        bars=clip.bars,
        waveform=clip.waveform,
        attack_ms=clip.attack_ms,
        decay_ms=clip.decay_ms,
        sustain_level=clip.sustain,
        release_ms=clip.release_ms,
        cutoff_hz=(
            20_000.0
            if has_automation(project, track.instrument_plugin, "cutoff_hz")
            else clip.cutoff_hz
        ),
        gate=clip.gate,
        gain_db=0.0,
    )
    arranged += _synth_audio(project, spec)
    return _apply_output_gain(project, track, arranged)


def _apply_output_gain(
    project: Project,
    track: Track,
    samples: np.ndarray,
    *,
    base_gain_db: float = 0.0,
) -> np.ndarray:
    """Apply common clip gain plus an optional shared track gain envelope."""

    lane = track.output_gain_lane
    if lane is None:
        if math.isclose(base_gain_db, 0.0, abs_tol=1e-12):
            return samples
        return samples * db_gain(base_gain_db)
    point_frames = np.asarray(
        [project.timing.bar_to_frame(point.bar) for point in lane.points],
        dtype=np.float64,
    )
    point_values = np.asarray(
        [point.value for point in lane.points],
        dtype=np.float64,
    )
    positions = np.arange(samples.shape[0], dtype=np.float64)
    if lane.curve == "linear":
        values = np.interp(positions, point_frames, point_values)
    else:
        indices = np.searchsorted(point_frames, positions, side="right") - 1
        indices = np.clip(indices, 0, len(point_values) - 1)
        values = point_values[indices]
    return samples * np.power(10.0, (base_gain_db + values) / 20.0)[:, np.newaxis]


def _synth_automation(project: Project, track: Track, frames: int) -> dict[str, np.ndarray]:
    instrument = track.instrument_plugin
    if instrument is None or instrument.preset != "uniwave":
        return {}
    return {
        lane.parameter: parameter_values(project, instrument, lane.parameter, frames)
        for lane in project.automation_lanes
        if lane.target is instrument
    }


def _automation_base_gain(track: Track) -> float:
    instrument = track.instrument_plugin
    if instrument is None:
        return -6.0
    value = instrument.settings.get("gain_db", -6.0)
    return float(value) if isinstance(value, int | float) else -6.0


def _synth_audio(project: Project, spec: NativeSynthSpec) -> np.ndarray:
    samples = render_native_synth(
        spec,
        sample_rate=project.sample_rate,
        tempo_bpm=project.tempo,
        quarter_notes_per_bar=project.timing.quarter_notes_per_bar,
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


def _mix_channel(samples: np.ndarray, *, gain_db: float, pan: float) -> np.ndarray:
    output = samples * db_gain(gain_db)
    if pan < 0.0:
        output = output.copy()
        output[:, 1] *= 1.0 + pan
    elif pan > 0.0:
        output = output.copy()
        output[:, 0] *= 1.0 - pan
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


def _export_settings(
    project: Project,
    *,
    bit_depth: BitDepth,
    channels: OutputChannels,
    sample_rate: int | None,
    tail_seconds: float,
) -> _ExportSettings:
    if (
        not isinstance(bit_depth, int)
        or isinstance(bit_depth, bool)
        or bit_depth not in {16, 24, 32}
    ):
        raise ProjectError("WAV bit_depth must be 16, 24, or 32.")
    if channels not in {"mono", "stereo"}:
        raise ProjectError("WAV channels must be 'mono' or 'stereo'.")
    output_rate = project.sample_rate if sample_rate is None else sample_rate
    if not isinstance(output_rate, int) or not 8_000 <= output_rate <= 192_000:
        raise ProjectError("Output sample_rate must be between 8000 and 192000 Hz.")
    if not math.isfinite(tail_seconds) or not 0.0 <= tail_seconds <= 60.0:
        raise ProjectError("tail_seconds must be between 0 and 60 seconds.")
    return _ExportSettings(
        bit_depth=bit_depth,
        channels=channels,
        sample_rate=output_rate,
        tail_seconds=float(tail_seconds),
    )


def _prepare_export(
    samples: np.ndarray, source_rate: int, settings: _ExportSettings
) -> np.ndarray:
    output = np.asarray(samples, dtype=np.float64)
    if settings.channels == "mono":
        output = np.mean(output, axis=1, keepdims=True)
    if settings.sample_rate != source_rate:
        output = np.asarray(
            soxr.resample(output, source_rate, settings.sample_rate, quality="HQ"),
            dtype=np.float64,
        )
        if output.ndim == 1:
            output = output[:, np.newaxis]
    if settings.bit_depth != 32:
        output = np.clip(output, -1.0, 1.0)
    return output


def _write_wav(
    path: Path,
    samples: np.ndarray,
    sample_rate: int,
    *,
    bit_depth: BitDepth = 16,
) -> None:
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
            subtype={16: "PCM_16", 24: "PCM_24", 32: "FLOAT"}[bit_depth],
        )
        _normalize_wav_metadata(temporary)
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


def _normalize_wav_metadata(path: Path) -> None:
    """Remove time-dependent metadata that libsndfile adds to float WAV files."""

    with path.open("r+b") as stream:
        if stream.read(12)[:4] != b"RIFF":
            return
        while True:
            header = stream.read(8)
            if len(header) != 8:
                return
            chunk_name = header[:4]
            chunk_size = int.from_bytes(header[4:], "little")
            chunk_data = stream.tell()
            if chunk_name == b"PEAK" and chunk_size >= 8:
                stream.seek(chunk_data + 4)
                stream.write(b"\0\0\0\0")
                return
            stream.seek(chunk_data + chunk_size + (chunk_size % 2))


def _write_stem(
    path: Path,
    samples: np.ndarray,
    settings: _ExportSettings,
    *,
    name: str,
    kind: Literal["track", "bus", "master"],
) -> StemFile:
    _write_wav(
        path,
        samples,
        settings.sample_rate,
        bit_depth=settings.bit_depth,
    )
    return StemFile(
        name=name,
        kind=kind,
        path=path,
        sha256=_sha256(path),
        peak_dbfs=_peak_dbfs(samples),
    )


def _stem_filename(index: int, name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-") or "channel"
    return f"{index:02d}-{slug}.wav"


def _validate_stem_output(
    project: Project, directory: Path, protected: set[Path]
) -> None:
    """Check the container and legacy stem folders before creating anything."""

    _assert_safe_managed_path(project, directory, protected, "Stem output folder")
    if directory.exists() and not directory.is_dir():
        raise ProjectError(f"Stem output folder is not a directory: {directory}")
    if directory.is_dir():
        for child in directory.rglob("*"):
            if child.is_symlink():
                raise ProjectError(f"Stem output cannot contain a symlink: {child}")

    metadata = directory / _STEM_METADATA_DIRECTORY
    if metadata.exists() or metadata.is_symlink():
        _reject_symlink_components(metadata, project.root, "Stem metadata directory")
        if not metadata.is_dir():
            raise ProjectError(f"Stem metadata path is not a directory: {metadata}")


def _make_directory(
    path: Path, project: Project, protected: set[Path], label: str
) -> None:
    _assert_safe_managed_path(project, path, protected, label)
    if path.exists():
        if not path.is_dir():
            raise ProjectError(f"{label} is not a directory: {path}")
        return
    path.mkdir(parents=True)
    _assert_safe_managed_path(project, path, protected, label)


def _safe_stem_destination(project: Project, path: Path, protected: set[Path]) -> Path:
    _assert_safe_managed_path(project, path, protected, "Stem output")
    return path


def _assert_safe_managed_path(
    project: Project,
    path: Path,
    protected: set[Path],
    label: str,
) -> Path:
    """Resolve one managed path without following a project escape symlink."""

    _reject_symlink_components(path, project.root, label)
    resolved = path.resolve(strict=False)
    try:
        resolved.relative_to(project.root)
    except ValueError as error:
        raise ProjectError(f"{label} must stay inside the project folder: {path}") from error
    if resolved in protected:
        raise ProjectError(f"{label} would overwrite a protected project file: {resolved}")
    return resolved


def _reject_symlink_components(path: Path, root: Path, label: str) -> None:
    try:
        relative = path.relative_to(root)
    except ValueError as error:
        raise ProjectError(f"{label} must stay inside the project folder: {path}") from error
    current = root
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise ProjectError(f"{label} cannot pass through a symlink: {current}")


def _read_stem_manifest(
    project: Project, directory: Path, protected: set[Path]
) -> _StemManifest | None:
    metadata = directory / _STEM_METADATA_DIRECTORY
    manifest_path = metadata / _STEM_MANIFEST_FILENAME
    if not manifest_path.exists() and not manifest_path.is_symlink():
        return None
    _assert_safe_managed_path(project, manifest_path, protected, "Stem ownership manifest")
    if not manifest_path.is_file():
        raise ProjectError(f"Stem ownership manifest is not a file: {manifest_path}")
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ProjectError(
            f"Could not read stem ownership manifest {manifest_path}: {error}"
        ) from error
    if not isinstance(data, dict) or data.get("schema_version") != _STEM_MANIFEST_SCHEMA_VERSION:
        raise ProjectError(
            f"Stem ownership manifest has an unsupported schema: {manifest_path}"
        )

    generation_value = data.get("generation")
    if (
        isinstance(generation_value, bool)
        or not isinstance(generation_value, int)
        or generation_value < 1
    ):
        raise ProjectError(f"Stem ownership manifest has an invalid generation: {manifest_path}")
    generation_value = int(generation_value)
    directory_value = data.get("generation_directory")
    if not isinstance(directory_value, str):
        raise ProjectError(f"Stem ownership manifest has no generation directory: {manifest_path}")
    generation_relative = _manifest_relative(directory_value, "generation directory")
    if generation_relative.parts[:1] != ("generations",):
        raise ProjectError(f"Stem generation is outside its managed directory: {manifest_path}")
    generation = metadata / Path(generation_relative.as_posix())
    _assert_safe_managed_path(project, generation, protected, "Stem generation")
    if not generation.is_dir():
        raise ProjectError(f"Stem generation is missing: {generation}")

    raw_files = data.get("files")
    if not isinstance(raw_files, list):
        raise ProjectError(f"Stem ownership manifest has invalid files: {manifest_path}")
    files: list[tuple[str, str]] = []
    seen: set[str] = set()
    for raw_file in raw_files:
        if not isinstance(raw_file, dict):
            raise ProjectError(
                f"Stem ownership manifest has an invalid file entry: {manifest_path}"
            )
        relative_value = raw_file.get("path")
        sha256 = raw_file.get("sha256")
        if not isinstance(relative_value, str) or not isinstance(sha256, str):
            raise ProjectError(
                f"Stem ownership manifest has an invalid file entry: {manifest_path}"
            )
        relative = _manifest_relative(relative_value, "stem file")
        if relative.suffix.casefold() != ".wav" or relative.as_posix() in seen:
            raise ProjectError(
                f"Stem ownership manifest has a duplicate or invalid file: {manifest_path}"
            )
        if not re.fullmatch(r"[0-9a-f]{64}", sha256):
            raise ProjectError(f"Stem ownership manifest has an invalid checksum: {manifest_path}")
        candidate = generation / Path(relative.as_posix())
        _assert_safe_managed_path(project, candidate, protected, "Stem cleanup candidate")
        seen.add(relative.as_posix())
        files.append((relative.as_posix(), sha256))
    return _StemManifest(generation_value, generation, tuple(files))


def _manifest_relative(value: str, label: str) -> PurePosixPath:
    if not value or "\\" in value:
        raise ProjectError(f"Stem manifest {label} must be a safe relative path: {value!r}")
    relative = PurePosixPath(value)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise ProjectError(f"Stem manifest {label} must be a safe relative path: {value!r}")
    return relative


def _publish_stem_manifest(
    project: Project,
    directory: Path,
    protected: set[Path],
    manifest: _StemManifest,
) -> None:
    metadata = directory / _STEM_METADATA_DIRECTORY
    manifest_path = metadata / _STEM_MANIFEST_FILENAME
    _assert_safe_managed_path(project, manifest_path, protected, "Stem ownership manifest")
    _write_json_atomic(manifest_path, _manifest_data(manifest, metadata))


def _manifest_data(manifest: _StemManifest, metadata: Path) -> dict[str, object]:
    return {
        "schema_version": _STEM_MANIFEST_SCHEMA_VERSION,
        "generation": manifest.generation,
        "generation_directory": manifest.directory.relative_to(metadata).as_posix(),
        "files": [
            {"path": relative, "sha256": sha256}
            for relative, sha256 in sorted(manifest.files)
        ],
    }


def _write_json_atomic(path: Path, data: Mapping[str, object]) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(data, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _relocate_stem(item: StemFile, staging: Path, generation: Path) -> StemFile:
    return StemFile(
        name=item.name,
        kind=item.kind,
        path=generation / item.path.relative_to(staging),
        sha256=item.sha256,
        peak_dbfs=item.peak_dbfs,
    )


def _remove_stale_stems(
    directory: Path,
    expected: set[Path],
    *,
    ownership: Mapping[str, str] | None = None,
    project: Project | None = None,
    protected: set[Path] | None = None,
) -> None:
    """Remove only unchanged WAVs owned by the previous completed generation."""

    if ownership is None:
        return
    protected_paths = set() if protected is None else protected
    for relative, checksum in ownership.items():
        candidate = directory / Path(relative)
        if candidate in expected:
            continue
        if project is not None:
            _assert_safe_managed_path(
                project,
                candidate,
                protected_paths,
                "Stem cleanup candidate",
            )
        if candidate.is_symlink() or not candidate.is_file():
            continue
        try:
            unchanged = _sha256(candidate) == checksum
        except OSError:
            continue
        if unchanged:
            try:
                candidate.unlink()
            except OSError:
                continue


def _peak_dbfs(samples: np.ndarray) -> float | None:
    peak = float(np.max(np.abs(samples))) if samples.size else 0.0
    return None if peak == 0.0 else 20.0 * math.log10(peak)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


__all__ = ["RenderResult", "StemFile", "StemRenderResult"]
