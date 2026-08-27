"""Standard MIDI export for Prism drum and note tracks."""

from __future__ import annotations

import hashlib
import math
import os
import struct
from dataclasses import dataclass
from pathlib import Path

from prism.errors import ProjectError, RenderError
from prism.music import note_to_midi
from prism.plugins import STOCK_PLUGINS
from prism.project.builder import ClipPlacement, DrumClip, MidiClip, Project, Track

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
    total_ticks = sum(section.bars for section in project.sections)
    total_ticks *= project.beats_per_bar * TICKS_PER_BEAT
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
    tempo = int(round(60_000_000 / project.tempo))
    denominator_power = int(math.log2(project.beat_unit))
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
                    project.beats_per_bar,
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
    if isinstance(clip, MidiClip):
        program = STOCK_PLUGINS.get("instrument", clip.instrument).midi_program
        if program is None:
            raise ProjectError(f"Instrument {clip.instrument!r} has no MIDI program.")
        events.append((0, -2, bytes([0xC0 | channel, program])))
    section_start = 0
    for section in project.sections:
        section_ticks = section.bars * project.beats_per_bar * TICKS_PER_BEAT
        active = (
            {item.name for item in project.tracks}
            if section.tracks is None
            else set(section.tracks)
        )
        if not track.muted and track.name in active:
            for placement in track.clips_for(section):
                _section_events(
                    events,
                    placement,
                    channel,
                    section_start,
                    section_ticks,
                    project.beats_per_bar,
                )
        section_start += section_ticks
    events.append((total_ticks, 9, b"\xff\x2f\x00"))
    return _chunk(events)


def _section_events(
    events: list[tuple[int, int, bytes]],
    placement: ClipPlacement,
    channel: int,
    section_start: int,
    section_ticks: int,
    beats_per_bar: int,
) -> None:
    clip = placement.clip
    if not isinstance(clip, DrumClip | MidiClip):
        return
    clip_ticks = clip.bars * TICKS_PER_BEAT * beats_per_bar
    placement_start = round(placement.start_bar * beats_per_bar * TICKS_PER_BEAT)
    cycle = placement_start
    section_end = section_start + section_ticks
    while cycle < section_ticks:
        if isinstance(clip, DrumClip):
            boundaries = [
                round(index * clip_ticks / len(clip.pattern))
                for index in range(len(clip.pattern) + 1)
            ]
            for index, token in enumerate(clip.pattern):
                if token == "-":
                    continue
                start = section_start + cycle + boundaries[index]
                if start >= section_end:
                    continue
                step_ticks = max(1, boundaries[index + 1] - boundaries[index])
                drum_note = STOCK_PLUGINS.get("instrument", clip.preset).drum_note
                if drum_note is None:
                    raise ProjectError(f"Percussion instrument {clip.preset!r} has no MIDI note.")
                duration = min(120, step_ticks)
                end = min(section_end, start + duration)
                events.append((start, 1, bytes([0x90 | channel, drum_note, 100])))
                events.append((end, 0, bytes([0x80 | channel, drum_note, 0])))
        else:
            _midi_expression_events(
                events,
                clip,
                channel=channel,
                cycle_start=section_start + cycle,
                section_end=section_end,
            )
        cycle += clip_ticks
        if not placement.repeat:
            break


def _midi_expression_events(
    events: list[tuple[int, int, bytes]],
    clip: MidiClip,
    *,
    channel: int,
    cycle_start: int,
    section_end: int,
) -> None:
    for point in clip.pitch_bend:
        tick = cycle_start + round(point.beat * TICKS_PER_BEAT)
        if tick < section_end:
            events.append((tick, -1, _pitch_bend_message(channel, point.value)))
    for point in clip.modulation:
        tick = cycle_start + round(point.beat * TICKS_PER_BEAT)
        if tick < section_end:
            amount = min(127, max(0, round(point.value * 127.0)))
            events.append((tick, -1, bytes([0xB0 | channel, 1, amount])))
    for note in clip.events:
        start = cycle_start + round(note.start * TICKS_PER_BEAT)
        if start >= section_end:
            continue
        duration = max(1, round(note.duration * TICKS_PER_BEAT))
        end = min(section_end, start + duration)
        midi_note = note_to_midi(note.pitch)
        events.append((start, 1, bytes([0x90 | channel, midi_note, note.velocity])))
        events.append((end, 0, bytes([0x80 | channel, midi_note, 0])))


def _pitch_bend_message(channel: int, semitones: float) -> bytes:
    value = min(16_383, max(0, round(8_192 + semitones * 8_191 / 2.0)))
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
