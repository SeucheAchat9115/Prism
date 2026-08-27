"""Deterministic offline rendering for script-authored Prism projects."""

from __future__ import annotations

import hashlib
import math
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

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

    def __str__(self) -> str:
        return f"Rendered {self.duration_seconds:.2f}s to {self.path}"


def render_project(project: Project, output: str | Path) -> RenderResult:
    """Render every named section in order to a WAV file."""

    try:
        summary = project.validate()
        output_path = project._output_path(output, suffix=".wav")
        total_frames = summary.bars * project.frames_per_bar
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

        for bus in project.buses:
            if bus.muted:
                continue
            processed = process_effect_chain(project, bus.effects, bus_inputs[bus.name])
            mix += _mix_channel(processed, gain_db=bus.gain_db, pan=bus.pan)

        mix = process_effect_chain(project, project.master_effects, mix)
        mix *= db_gain(project.master_gain_db)
        peak = float(np.max(np.abs(mix))) if mix.size else 0.0
        target = 10.0 ** (-1.0 / 20.0)
        if project.normalize and peak > target:
            mix *= target / peak
            peak = target
        mix = np.clip(mix, -1.0, 1.0)
        _write_wav(output_path, mix, project.sample_rate)
        digest = _sha256(output_path)
        result = RenderResult(
            path=output_path,
            sample_rate=project.sample_rate,
            channels=2,
            frames=total_frames,
            duration_seconds=total_frames / project.sample_rate,
            sha256=digest,
            peak_dbfs=None if peak == 0.0 else 20.0 * math.log10(peak),
        )
        return result
    except (ProjectError, RenderError):
        raise
    except (OSError, RuntimeError, ValueError) as error:
        raise RenderError(f"Could not render {project.name!r}: {error}") from error


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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


__all__ = ["RenderResult"]
