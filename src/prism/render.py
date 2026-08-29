"""Deterministic offline rendering for script-authored Prism projects."""

from __future__ import annotations

import hashlib
import math
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np
import soundfile as sf
import soxr

from prism.effects import (
    has_automation,
    parameter_values,
    process_effect_chain,
    process_track_plugins,
)
from prism.errors import ProjectError, RenderError
from prism.music import ControlPoint, Note, db_gain
from prism.project.builder import (
    AudioClip,
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

    @property
    def files(self) -> tuple[StemFile, ...]:
        """Return every track, bus, and master file in render order."""

        return (*self.tracks, *self.buses, self.master)

    def __str__(self) -> str:
        count = len(self.tracks) + len(self.buses) + 1
        return f"Rendered {count} aligned stem files to {self.directory}"


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
    """Render aligned track, bus/return, and master WAV files."""

    try:
        directory = project._output_directory(output)
        settings = _export_settings(
            project,
            bit_depth=bit_depth,
            channels=channels,
            sample_rate=sample_rate,
            tail_seconds=tail_seconds,
        )
        rendered = _render_buffers(project, tail_seconds=settings.tail_seconds)
        track_files = tuple(
            _write_stem(
                directory / "tracks" / _stem_filename(index, name),
                _prepare_export(rendered.tracks[name], project.sample_rate, settings),
                settings,
                name=name,
                kind="track",
            )
            for index, name in enumerate(rendered.tracks, start=1)
        )
        bus_files = tuple(
            _write_stem(
                directory / "buses" / _stem_filename(index, name),
                _prepare_export(rendered.buses[name], project.sample_rate, settings),
                settings,
                name=name,
                kind="bus",
            )
            for index, name in enumerate(rendered.buses, start=1)
        )
        master_samples = _prepare_export(rendered.master, project.sample_rate, settings)
        master = _write_stem(
            directory / "master.wav",
            master_samples,
            settings,
            name="Master",
            kind="master",
        )
        _remove_stale_stems(directory / "tracks", {item.path for item in track_files})
        _remove_stale_stems(directory / "buses", {item.path for item in bus_files})
        return StemRenderResult(
            directory=directory,
            sample_rate=settings.sample_rate,
            channels=1 if settings.channels == "mono" else 2,
            frames=master_samples.shape[0],
            duration_seconds=master_samples.shape[0] / settings.sample_rate,
            bit_depth=settings.bit_depth,
            tail_seconds=settings.tail_seconds,
            tracks=track_files,
            buses=bus_files,
            master=master,
        )
    except (ProjectError, RenderError):
        raise
    except (OSError, RuntimeError, ValueError) as error:
        raise RenderError(f"Could not render stems for {project.name!r}: {error}") from error


def _render_buffers(project: Project, *, tail_seconds: float = 0.0) -> _RenderedProject:
    summary = project.validate()
    song_frames = summary.bars * project.frames_per_bar
    tail_frames = int(round(tail_seconds * project.sample_rate))
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
            clip_buffers = {
                id(placement): _clip_buffer(project, track, placement.clip)
                for placement in track.clips
            }
            arranged = np.zeros((total_frames, 2), dtype=np.float64)
            cursor = 0
            for section in project.sections:
                frames = section.bars * project.frames_per_bar
                active = (
                    {item.name for item in project.tracks}
                    if section.tracks is None
                    else set(section.tracks)
                )
                if track.name in active:
                    for placement in track.clips_for(section):
                        offset = int(round(placement.start_bar * project.frames_per_bar))
                        available = frames - offset
                        if available <= 0:
                            continue
                        source = clip_buffers[id(placement)]
                        placed = (
                            _loop_to(source, available)
                            if placement.repeat
                            else _fit_to(source, available)
                        )
                        start = cursor + offset
                        arranged[start : start + available] += placed
                cursor += frames
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


def _clip_buffer(project: Project, track: Track, clip: TrackClip) -> np.ndarray:
    if isinstance(clip, SampleClip):
        source = _prepare_audio(project, clip)
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
        source = _prepare_audio(project, clip)
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
    start = int(round(clip.start_seconds * project.sample_rate))
    end = (
        source.shape[0]
        if clip.end_seconds is None
        else int(round(clip.end_seconds * project.sample_rate))
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
        target_frames = max(1, int(round(clip.stretch_bars * project.frames_per_bar)))
        source = _time_resize(source, target_frames)
    if clip.fade_in_ms > 0.0:
        fade_frames = min(
            source.shape[0], int(round(clip.fade_in_ms * project.sample_rate / 1_000.0))
        )
        if fade_frames:
            source[:fade_frames] *= np.linspace(
                0.0, 1.0, fade_frames, endpoint=True
            )[:, np.newaxis]
    if clip.fade_out_ms > 0.0:
        fade_frames = min(
            source.shape[0], int(round(clip.fade_out_ms * project.sample_rate / 1_000.0))
        )
        if fade_frames:
            source[-fade_frames:] *= np.linspace(
                1.0, 0.0, fade_frames, endpoint=True
            )[:, np.newaxis]
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
    """Render MIDI placements as global events so synth automation follows arrangement time."""

    arranged = np.zeros((total_frames, 2), dtype=np.float64)
    automation = _synth_automation(project, track, total_frames)
    cursor_bar = 0.0
    for section in project.sections:
        active = section.tracks is None or track.name in section.tracks
        if active:
            for placement in track.clips_for(section):
                clip = placement.clip
                assert isinstance(clip, MidiClip)
                start_bar = cursor_bar + placement.start_bar
                available_beats = (
                    section.bars - placement.start_bar
                ) * project.beats_per_bar
                if available_beats <= 0:
                    continue
                events: list[Note] = []
                bends: list[ControlPoint] = []
                modulations: list[ControlPoint] = []
                repeats = (
                    max(1, math.ceil(available_beats / (clip.bars * project.beats_per_bar)))
                    if placement.repeat
                    else 1
                )
                for repeat_index in range(repeats):
                    repeat_beats = repeat_index * clip.bars * project.beats_per_bar
                    for note in clip.events:
                        start = repeat_beats + note.start
                        if start < available_beats:
                            duration = min(note.duration, available_beats - start)
                            events.append(
                                Note(
                                    note.pitch,
                                    start=start_bar * project.beats_per_bar + start,
                                    duration=duration,
                                    velocity=note.velocity,
                                )
                            )
                    for point in clip.pitch_bend:
                        if repeat_beats + point.beat <= available_beats:
                            bends.append(
                                ControlPoint(
                                    start_bar * project.beats_per_bar + repeat_beats + point.beat,
                                    point.value,
                                )
                            )
                    for point in clip.modulation:
                        if repeat_beats + point.beat <= available_beats:
                            modulations.append(
                                ControlPoint(
                                    start_bar * project.beats_per_bar + repeat_beats + point.beat,
                                    point.value,
                                )
                            )
                if not events:
                    continue
                instrument = track.instrument_plugin
                if instrument is not None and instrument.vst3 is not None:
                    from prism.vst_host import render_vst3_instrument

                    rendered = render_vst3_instrument(
                        project,
                        instrument,
                        events,
                        bends,
                        modulations,
                        total_frames,
                    )
                    arranged += rendered * db_gain(clip.gain_db)
                    continue
                spec = NativeSynthSpec(
                    preset=clip.instrument,
                    sequence=clip.notes,
                    note_events=tuple(events),
                    pitch_bend=tuple(bends),
                    modulation=tuple(modulations),
                    uniwave=clip.uniwave,
                    automation=automation,
                    automation_base_gain_db=(
                        _automation_base_gain(track)
                        if automation
                        else None
                    ),
                    frame_count=total_frames,
                    bars=total_bars,
                    waveform=clip.waveform,
                    attack_ms=clip.attack_ms,
                    decay_ms=clip.decay_ms,
                    sustain_level=clip.sustain,
                    release_ms=clip.release_ms,
                    cutoff_hz=clip.cutoff_hz,
                    gate=clip.gate,
                    gain_db=clip.gain_db,
                )
                arranged += _synth_audio(project, spec)
        cursor_bar += section.bars
    return arranged


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


def _remove_stale_stems(directory: Path, expected: set[Path]) -> None:
    if not directory.is_dir():
        return
    for path in directory.iterdir():
        if path.is_file() and path.suffix.casefold() == ".wav" and path not in expected:
            path.unlink()


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
