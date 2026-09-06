"""Standard MIDI export for Prism drum and note tracks."""

from __future__ import annotations

import hashlib
import os
import struct
from dataclasses import dataclass
from pathlib import Path

from prism.arrangement import (
    MIDI_MODULATION_STEPS,
    MIDI_PITCH_BEND_STEPS,
    compile_track_events,
)
from prism.errors import ProjectError, RenderError
from prism.plugins import STOCK_PLUGINS
from prism.project.builder import DrumClip, MidiClip, Project, Track

TICKS_PER_BEAT = 480


@dataclass(frozen=True, slots=True)
class MidiResult:
    """Facts about a completed standard MIDI file."""

    path: Path
    tracks: int
    ticks_per_beat: int
    sha256: str

    def __str__(self) -> str:
        noun = "track" if self.tracks == 1 else "tracks"
        return f"Exported {self.tracks} MIDI {noun} to {self.path}"


def export_midi(project: Project, output: str | Path) -> MidiResult:
    """Export arranged built-in drum and MIDI tracks as a format-1 MIDI file."""

    project.validate()
    path = project._output_path(output, suffix=".mid")
    music_tracks = [
        track for track in project.tracks if isinstance(track.clip, DrumClip | MidiClip)
    ]
    if not music_tracks:
        raise ProjectError("The project has no built-in drum or MIDI tracks to export.")
    total_bars = sum(section.bars for section in project.sections)
    total_ticks = project.timing.bars_to_ticks(total_bars, TICKS_PER_BEAT)
    chunks = [_conductor_track(project, total_ticks)]
    melodic_index = 0
    for track in music_tracks:
        clip = track.clip
        assert isinstance(clip, DrumClip | MidiClip)
        if isinstance(clip, DrumClip):
            channel = 9
        else:
            channel = melodic_index
            if channel >= 9:
                channel += 1
            melodic_index += 1
            if channel > 15:
                raise ProjectError("A MIDI export supports at most 15 melodic tracks.")
        chunks.append(_music_track(project, track, channel, total_ticks))
    header = b"MThd" + struct.pack(">IHHH", 6, 1, len(chunks), TICKS_PER_BEAT)
    payload = header + b"".join(chunks)
    _write_atomic(path, payload)
    return MidiResult(
        path=path,
        tracks=len(music_tracks),
        ticks_per_beat=TICKS_PER_BEAT,
        sha256=hashlib.sha256(payload).hexdigest(),
    )


def _conductor_track(project: Project, total_ticks: int) -> bytes:
    timing = project.timing
    tempo = timing.microseconds_per_quarter_note
    denominator_power = timing.denominator_power
    events = [
        (0, -3, _meta_text(0x03, project.name)),
        (0, -2, b"\xff\x51\x03" + tempo.to_bytes(3, "big")),
        (
            0,
            -1,
            bytes(
                [
                    0xFF,
                    0x58,
                    0x04,
                    timing.numerator,
                    denominator_power,
                    24,
                    8,
                ]
            ),
        ),
        (total_ticks, 9, b"\xff\x2f\x00"),
    ]
    return _chunk(events)


def _music_track(project: Project, track: Track, channel: int, total_ticks: int) -> bytes:
    clip = track.clip
    assert isinstance(clip, DrumClip | MidiClip)
    events: list[tuple[int, int, bytes]] = [(0, -3, _meta_text(0x03, track.name))]
    if isinstance(clip, MidiClip) and (
        track.instrument_plugin is None or track.instrument_plugin.vst3 is None
    ):
        program = STOCK_PLUGINS.get("instrument", clip.instrument).midi_program
        if program is None:
            raise ProjectError(f"Instrument {clip.instrument!r} has no MIDI program.")
        events.append((0, -2, bytes([0xC0 | channel, program])))
    total_bars = sum(section.bars for section in project.sections)
    stream = compile_track_events(
        project,
        track,
        total_bars=total_bars,
        total_frames=project.timing.bars_to_frame(total_bars),
    )
    if not track.muted:
        for event in stream.events:
            if event.kind not in {"note_on", "note_off"}:
                continue
            assert event.midi_note is not None
            tick = project.timing.quarter_notes_to_ticks(event.beat, TICKS_PER_BEAT)
            velocity = event.velocity if event.velocity is not None else 0
            status = 0x90 if event.kind == "note_on" else 0x80
            order = 0 if event.kind == "note_off" else 5
            events.append((tick, order, bytes([status | channel, event.midi_note, velocity])))
        for controller in stream.midi_controller_events(TICKS_PER_BEAT):
            if controller.controller == "pitch_bend":
                payload = _pitch_bend_message(
                    channel,
                    controller.value,
                    controller.pitch_bend_range,
                )
                order = 3
            else:
                amount = min(MIDI_MODULATION_STEPS, max(0, round(controller.value * 127.0)))
                payload = bytes([0xB0 | channel, 1, amount])
                order = 4
            events.append((controller.tick, order, payload))
    events.append((total_ticks, 9, b"\xff\x2f\x00"))
    return _chunk(events)


def _pitch_bend_message(channel: int, semitones: float, bend_range: float = 2.0) -> bytes:
    if bend_range <= 0.0:
        raise RenderError("MIDI pitch-bend range must be positive.")
    value = min(
        MIDI_PITCH_BEND_STEPS,
        max(0, round(8_192 + semitones * 8_191 / bend_range)),
    )
    return bytes([0xE0 | channel, value & 0x7F, (value >> 7) & 0x7F])


def _chunk(events: list[tuple[int, int, bytes]]) -> bytes:
    payload = bytearray()
    previous = 0
    for tick, _, message in sorted(events, key=lambda item: (item[0], item[1], item[2])):
        payload.extend(_variable_length(tick - previous))
        payload.extend(message)
        previous = tick
    return b"MTrk" + struct.pack(">I", len(payload)) + bytes(payload)


def _meta_text(kind: int, value: str) -> bytes:
    payload = value.encode("utf-8")
    return bytes([0xFF, kind]) + _variable_length(len(payload)) + payload


def _variable_length(value: int) -> bytes:
    if value < 0:
        raise RenderError("MIDI events are not in chronological order.")
    buffer = value & 0x7F
    output = bytearray([buffer])
    while value >> 7:
        value >>= 7
        buffer = (value & 0x7F) | 0x80
        output.insert(0, buffer)
    return bytes(output)


def _write_atomic(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".mid.tmp")
    try:
        temporary.write_bytes(payload)
        os.replace(temporary, path)
    except OSError as error:
        raise RenderError(f"Could not write MIDI file {path}: {error}") from error
    finally:
        temporary.unlink(missing_ok=True)


__all__ = ["MidiResult"]
