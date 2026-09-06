"""Compile script-authored MIDI placements into one deterministic event stream.

The project model stores notes and controller points relative to a clip.  This
module is the single arrangement boundary: every consumer receives the same
absolute musical/sample positions, clip occurrences, controller policy, and
stable note identities.  MIDI is still a discrete format, so continuous
controllers are sampled at most 24 ticks apart (at the default 480 ticks per
quarter note) before serialization.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Literal

from prism.errors import ProjectError
from prism.music import (
    ControlCurve,
    ControllerBoundaryMode,
    ControlPoint,
    note_to_midi,
)

if TYPE_CHECKING:
    from prism.project.builder import ClipPlacement, Project, Track
    from prism.timing import TimingMap


ControllerName = Literal["pitch_bend", "modulation"]
MusicalEventKind = Literal[
    "clip_start",
    "clip_end",
    "controller",
    "note_on",
    "note_off",
]

# A 24-tick spacing at 480 ticks/quarter is 1/20 of a quarter note.  The
# exported MIDI therefore documents a bounded approximation instead of making
# a few authored points look like a continuous ramp to a receiving device.
MIDI_CONTROLLER_TICK_STEP = 24
MIDI_PITCH_BEND_STEPS = 16_383
MIDI_MODULATION_STEPS = 127

_NOTE_OFF_ORDER = 0
_CLIP_END_ORDER = 1
_CLIP_START_ORDER = 2
_CONTROLLER_RESET_ORDER = 3
_CONTROLLER_ORDER = 4
_NOTE_ON_ORDER = 5


@dataclass(frozen=True, slots=True)
class CompiledClipBoundary:
    """One concrete occurrence of a source clip in the arrangement."""

    clip_id: str
    section: str
    placement_index: int
    repeat_index: int
    start_beat: float
    end_beat: float
    start_frame: int
    end_frame: int
    repeat: bool
    gain_db: float


@dataclass(frozen=True, slots=True)
class CompiledNote:
    """A note occurrence with stable identity and absolute positions."""

    note_id: str
    pitch: str | None
    midi_note: int
    velocity: int
    on_beat: float
    off_beat: float
    on_frame: int
    off_frame: int
    clip_id: str
    gain_db: float
    sequence: int


@dataclass(frozen=True, slots=True)
class CompiledControllerEvent:
    """One controller point in the compiled absolute event stream."""

    controller: ControllerName
    beat: float
    frame: int
    value: float
    curve: ControlCurve
    clip_id: str
    pitch_bend_range: float
    synthetic_reset: bool
    sequence: int


@dataclass(frozen=True, slots=True)
class MusicalEvent:
    """One ordered event in a :class:`CompiledTrackEvents` stream."""

    kind: MusicalEventKind
    beat: float
    frame: int
    order: int
    sequence: int
    clip_id: str | None = None
    note_id: str | None = None
    midi_note: int | None = None
    velocity: int | None = None
    controller: ControllerName | None = None
    value: float | None = None
    curve: ControlCurve | None = None
    pitch_bend_range: float | None = None
    synthetic_reset: bool = False


@dataclass(frozen=True, slots=True)
class MidiControllerEvent:
    """A sampled controller point ready for a MIDI serializer."""

    tick: int
    controller: ControllerName
    value: float
    pitch_bend_range: float
    sequence: int


@dataclass(frozen=True, slots=True)
class CompiledTrackEvents:
    """The complete compiled musical stream for one drum or MIDI track."""

    track_name: str
    total_beats: float
    total_frames: int
    notes: tuple[CompiledNote, ...]
    controllers: tuple[CompiledControllerEvent, ...]
    boundaries: tuple[CompiledClipBoundary, ...]
    events: tuple[MusicalEvent, ...]
    controller_boundary: ControllerBoundaryMode
    pitch_bend_range: float

    def controller_points(self, controller: ControllerName) -> tuple[ControlPoint, ...]:
        """Return absolute controller points for native audio rendering."""

        return tuple(
            ControlPoint(point.beat, point.value, point.curve)
            for point in self.controllers
            if point.controller == controller
        )

    def controller_chase(
        self,
        beat: float,
        *,
        timing: TimingMap,
    ) -> tuple[CompiledControllerEvent, ...]:
        """Return controller values to restore state at a transport position.

        A chase is always a hold point.  It is useful when a future transport
        starts in the middle of a song and when the current task keeps VST
        placement renders isolated while sharing the same compiled source.
        """

        if not math.isfinite(beat) or beat < 0.0:
            raise ProjectError("Controller chase position must be finite and zero or greater.")
        result: list[CompiledControllerEvent] = []
        controller_defaults: tuple[tuple[ControllerName, float], ...] = (
            ("pitch_bend", 0.0),
            ("modulation", 0.0),
        )
        for controller, default in controller_defaults:
            points = [
                point
                for point in self.controllers
                if point.controller == controller and point.beat <= beat + 1e-9
            ]
            if points:
                current = max(points, key=lambda point: (point.beat, point.sequence))
                value = current.value
                bend_range = current.pitch_bend_range
            else:
                value = default
                bend_range = self.pitch_bend_range
            result.append(
                CompiledControllerEvent(
                    controller=controller,
                    beat=float(beat),
                    frame=timing.quarter_notes_to_frame(beat),
                    value=value,
                    curve="hold",
                    clip_id="__chase__",
                    pitch_bend_range=bend_range,
                    synthetic_reset=True,
                    sequence=-2 if controller == "pitch_bend" else -1,
                )
            )
        return tuple(result)

    def reset_controller_events(
        self,
        beat: float,
        *,
        timing: TimingMap,
    ) -> tuple[CompiledControllerEvent, ...]:
        """Return explicit zero-valued controller resets at ``beat``."""

        return _reset_controller_events(
            beat,
            frame=timing.quarter_notes_to_frame(beat),
            pitch_bend_range=self.pitch_bend_range,
            clip_id="__reset__",
            sequence_start=-2,
        )

    def for_boundary(
        self,
        boundary: CompiledClipBoundary,
        *,
        timing: TimingMap,
    ) -> "CompiledTrackEvents":
        """Return a scoped stream for one placement occurrence.

        The source is still the per-track compilation.  A retained controller
        is chased into an isolated consumer so VST placement renders do not
        accidentally depend on whichever placement happened to render first.
        Continuous one-instance VST processing remains a later task.
        """

        notes = tuple(note for note in self.notes if note.clip_id == boundary.clip_id)
        controllers = [
            point for point in self.controllers if point.clip_id == boundary.clip_id
        ]
        if self.controller_boundary == "retain":
            controllers = [
                *self.controller_chase(boundary.start_beat, timing=timing),
                *controllers,
            ]
        controllers.sort(key=_controller_sort_key)
        selected_events = [
            event
            for event in self.events
            if event.clip_id == boundary.clip_id and event.kind != "controller"
        ]
        selected_events.extend(
            _controller_musical_event(point)
            for point in controllers
            if point.clip_id == boundary.clip_id or point.clip_id == "__chase__"
        )
        selected_events.sort(key=_event_sort_key)
        return CompiledTrackEvents(
            track_name=self.track_name,
            total_beats=self.total_beats,
            total_frames=self.total_frames,
            notes=notes,
            controllers=tuple(controllers),
            boundaries=(boundary,),
            events=tuple(selected_events),
            controller_boundary=self.controller_boundary,
            pitch_bend_range=self.pitch_bend_range,
        )

    def midi_controller_events(
        self,
        ticks_per_beat: int,
    ) -> tuple[MidiControllerEvent, ...]:
        """Resample continuous curves into bounded discrete MIDI events."""

        if isinstance(ticks_per_beat, bool) or not isinstance(ticks_per_beat, int):
            raise ValueError("ticks_per_beat must be a positive integer.")
        if ticks_per_beat <= 0:
            raise ValueError("ticks_per_beat must be a positive integer.")
        result: list[MidiControllerEvent] = []
        for controller in ("pitch_bend", "modulation"):
            points = [
                point for point in self.controllers if point.controller == controller
            ]
            result.extend(_resample_controller(points, ticks_per_beat))
        return tuple(sorted(result, key=lambda event: (event.tick, event.sequence)))


def compile_track_events(
    project: Project,
    track: Track,
    *,
    total_bars: int,
    total_frames: int,
) -> CompiledTrackEvents:
    """Compile one track's scoped/repeated clips into absolute events."""

    # Keep the runtime import here: the builder owns the public model and must
    # remain importable without importing this arrangement consumer module.
    from prism.project.builder import DrumClip, MidiClip

    if not track.clips or not isinstance(track.clip, DrumClip | MidiClip):
        raise ProjectError(f"Track {track.name!r} has no MIDI-compatible clip.")
    timing = project.timing
    total_beats = timing.bars_to_quarter_notes(total_bars)
    boundary_mode = project.controller_boundary
    first_clip = track.clip
    pitch_bend_range = (
        first_clip.pitch_bend_range if isinstance(first_clip, MidiClip) else 2.0
    )
    notes: list[CompiledNote] = []
    controllers: list[CompiledControllerEvent] = []
    boundaries: list[CompiledClipBoundary] = []
    events: list[MusicalEvent] = []
    sequence = 0

    def add_event(event: MusicalEvent) -> None:
        nonlocal sequence
        events.append(event)
        sequence = max(sequence, event.sequence + 1)

    if isinstance(first_clip, MidiClip) and boundary_mode in {"reset", "retain"}:
        for point in _reset_controller_events(
            0.0,
            frame=0,
            pitch_bend_range=pitch_bend_range,
            clip_id="__initial__",
            sequence_start=sequence,
        ):
            controllers.append(point)
            add_event(_controller_musical_event(point))

    section_cursor_beats = 0.0
    for section_index, section in enumerate(project.sections):
        section_beats = timing.bars_to_quarter_notes(section.bars)
        section_end = section_cursor_beats + section_beats
        active = section.tracks is None or track.name in section.tracks
        if active:
            for placement_index, placement in _selected_placements(track, section.name):
                clip = placement.clip
                if not isinstance(clip, DrumClip | MidiClip):
                    continue
                placement_start = section_cursor_beats + timing.bars_to_quarter_notes(
                    placement.start_bar
                )
                clip_beats = timing.bars_to_quarter_notes(clip.bars)
                available = section_end - placement_start
                if available <= 0.0:
                    continue
                repeats = max(1, math.ceil(available / clip_beats)) if placement.repeat else 1
                for repeat_index in range(repeats):
                    start_beat = placement_start + repeat_index * clip_beats
                    if start_beat >= section_end or start_beat >= total_beats:
                        continue
                    end_beat = min(section_end, start_beat + clip_beats, total_beats)
                    if end_beat <= start_beat:
                        continue
                    clip_id = (
                        f"{track.name}/section-{section_index}:{section.name}/"
                        f"placement-{placement_index}/repeat-{repeat_index}"
                    )
                    boundary = CompiledClipBoundary(
                        clip_id=clip_id,
                        section=section.name,
                        placement_index=placement_index,
                        repeat_index=repeat_index,
                        start_beat=start_beat,
                        end_beat=end_beat,
                        start_frame=timing.quarter_notes_to_frame(start_beat),
                        end_frame=timing.quarter_notes_to_frame(end_beat),
                        repeat=placement.repeat,
                        gain_db=clip.gain_db,
                    )
                    boundaries.append(boundary)
                    add_event(
                        MusicalEvent(
                            kind="clip_start",
                            beat=start_beat,
                            frame=boundary.start_frame,
                            order=_CLIP_START_ORDER,
                            sequence=sequence,
                            clip_id=clip_id,
                        )
                    )
                    if isinstance(clip, MidiClip):
                        if boundary_mode == "reset":
                            for point in _reset_controller_events(
                                start_beat,
                                frame=boundary.start_frame,
                                pitch_bend_range=clip.pitch_bend_range,
                                clip_id=clip_id,
                                sequence_start=sequence,
                            ):
                                controllers.append(point)
                                add_event(_controller_musical_event(point))
                        _compile_midi_clip(
                            clip,
                            boundary,
                            timing=timing,
                            notes=notes,
                            controllers=controllers,
                            add_event=add_event,
                            sequence_start=sequence,
                        )
                    else:
                        _compile_drum_clip(
                            clip,
                            boundary,
                            timing=timing,
                            notes=notes,
                            add_event=add_event,
                            sequence_start=sequence,
                        )
                    add_event(
                        MusicalEvent(
                            kind="clip_end",
                            beat=end_beat,
                            frame=boundary.end_frame,
                            order=_CLIP_END_ORDER,
                            sequence=sequence,
                            clip_id=clip_id,
                        )
                    )
        section_cursor_beats = section_end

    notes.sort(key=lambda note: (note.on_frame, note.off_frame, note.sequence))
    controllers.sort(key=_controller_sort_key)
    events.sort(key=_event_sort_key)
    return CompiledTrackEvents(
        track_name=track.name,
        total_beats=total_beats,
        total_frames=total_frames,
        notes=tuple(notes),
        controllers=tuple(controllers),
        boundaries=tuple(boundaries),
        events=tuple(events),
        controller_boundary=boundary_mode,
        pitch_bend_range=pitch_bend_range,
    )


def _selected_placements(
    track: Track, section_name: str
) -> tuple[tuple[int, ClipPlacement], ...]:
    placements = tuple(enumerate(track.clips))
    scoped = tuple((index, item) for index, item in placements if item.section == section_name)
    if scoped:
        return scoped
    return tuple((index, item) for index, item in placements if item.section is None)


def _compile_midi_clip(
    clip: object,
    boundary: CompiledClipBoundary,
    *,
    timing: TimingMap,
    notes: list[CompiledNote],
    controllers: list[CompiledControllerEvent],
    add_event: Callable[[MusicalEvent], None],
    sequence_start: int,
) -> None:
    from prism.project.builder import MidiClip

    assert isinstance(clip, MidiClip)
    sequence = sequence_start
    for note_index, note in enumerate(clip.events):
        on_beat = boundary.start_beat + note.start
        off_beat = min(boundary.end_beat, on_beat + note.duration)
        if on_beat >= boundary.end_beat or off_beat <= on_beat:
            continue
        on_frame = timing.quarter_notes_to_frame(on_beat)
        if on_frame >= boundary.end_frame:
            continue
        off_frame = min(
            boundary.end_frame,
            max(on_frame + 1, timing.quarter_notes_to_frame(off_beat)),
        )
        note_id = f"{boundary.clip_id}/note-{note_index}"
        compiled = CompiledNote(
            note_id=note_id,
            pitch=note.pitch,
            midi_note=note_to_midi(note.pitch),
            velocity=note.velocity,
            on_beat=on_beat,
            off_beat=off_beat,
            on_frame=on_frame,
            off_frame=off_frame,
            clip_id=boundary.clip_id,
            gain_db=boundary.gain_db,
            sequence=sequence,
        )
        notes.append(compiled)
        add_event(
            MusicalEvent(
                kind="note_on",
                beat=on_beat,
                frame=on_frame,
                order=_NOTE_ON_ORDER,
                sequence=sequence,
                clip_id=boundary.clip_id,
                note_id=note_id,
                midi_note=compiled.midi_note,
                velocity=note.velocity,
            )
        )
        sequence += 1
        add_event(
            MusicalEvent(
                kind="note_off",
                beat=off_beat,
                frame=off_frame,
                order=_NOTE_OFF_ORDER,
                sequence=sequence,
                clip_id=boundary.clip_id,
                note_id=note_id,
                midi_note=compiled.midi_note,
                velocity=0,
            )
        )
        sequence += 1
    controller_points: tuple[
        tuple[ControllerName, Sequence[ControlPoint]], ...
    ] = (
        ("pitch_bend", clip.pitch_bend),
        ("modulation", clip.modulation),
    )
    for controller, points in controller_points:
        for point in points:
            beat = boundary.start_beat + point.beat
            if beat > boundary.end_beat + 1e-9:
                continue
            compiled_point = CompiledControllerEvent(
                controller=controller,
                beat=beat,
                frame=timing.quarter_notes_to_frame(beat),
                value=point.value,
                curve=point.curve,
                clip_id=boundary.clip_id,
                pitch_bend_range=clip.pitch_bend_range,
                synthetic_reset=False,
                sequence=sequence,
            )
            controllers.append(compiled_point)
            add_event(_controller_musical_event(compiled_point))
            sequence += 1


def _compile_drum_clip(
    clip: object,
    boundary: CompiledClipBoundary,
    *,
    timing: TimingMap,
    notes: list[CompiledNote],
    add_event: Callable[[MusicalEvent], None],
    sequence_start: int,
) -> None:
    from prism.plugins import STOCK_PLUGINS
    from prism.project.builder import DrumClip

    assert isinstance(clip, DrumClip)
    drum_note = STOCK_PLUGINS.get("instrument", clip.preset).drum_note
    if drum_note is None:
        raise ProjectError(f"Percussion instrument {clip.preset!r} has no MIDI note.")
    step = (boundary.end_beat - boundary.start_beat) / len(clip.pattern)
    sequence = sequence_start
    for index, token in enumerate(clip.pattern):
        if token == "-":
            continue
        on_beat = boundary.start_beat + index * step
        off_beat = min(boundary.end_beat, on_beat + min(0.25, step))
        on_frame = timing.quarter_notes_to_frame(on_beat)
        off_frame = min(
            boundary.end_frame,
            max(on_frame + 1, timing.quarter_notes_to_frame(off_beat)),
        )
        note_id = f"{boundary.clip_id}/hit-{index}"
        notes.append(
            CompiledNote(
                note_id=note_id,
                pitch=None,
                midi_note=drum_note,
                velocity=100,
                on_beat=on_beat,
                off_beat=off_beat,
                on_frame=on_frame,
                off_frame=off_frame,
                clip_id=boundary.clip_id,
                gain_db=boundary.gain_db,
                sequence=sequence,
            )
        )
        add_event(
            MusicalEvent(
                kind="note_on",
                beat=on_beat,
                frame=on_frame,
                order=_NOTE_ON_ORDER,
                sequence=sequence,
                clip_id=boundary.clip_id,
                note_id=note_id,
                midi_note=drum_note,
                velocity=100,
            )
        )
        sequence += 1
        add_event(
            MusicalEvent(
                kind="note_off",
                beat=off_beat,
                frame=off_frame,
                order=_NOTE_OFF_ORDER,
                sequence=sequence,
                clip_id=boundary.clip_id,
                note_id=note_id,
                midi_note=drum_note,
                velocity=0,
            )
        )
        sequence += 1


def _reset_controller_events(
    beat: float,
    *,
    frame: int,
    pitch_bend_range: float,
    clip_id: str,
    sequence_start: int,
) -> tuple[CompiledControllerEvent, ...]:
    return (
        CompiledControllerEvent(
            controller="pitch_bend",
            beat=beat,
            frame=frame,
            value=0.0,
            curve="hold",
            clip_id=clip_id,
            pitch_bend_range=pitch_bend_range,
            synthetic_reset=True,
            sequence=sequence_start,
        ),
        CompiledControllerEvent(
            controller="modulation",
            beat=beat,
            frame=frame,
            value=0.0,
            curve="hold",
            clip_id=clip_id,
            pitch_bend_range=pitch_bend_range,
            synthetic_reset=True,
            sequence=sequence_start + 1,
        ),
    )


def _controller_musical_event(point: CompiledControllerEvent) -> MusicalEvent:
    return MusicalEvent(
        kind="controller",
        beat=point.beat,
        frame=point.frame,
        order=_CONTROLLER_RESET_ORDER if point.synthetic_reset else _CONTROLLER_ORDER,
        sequence=point.sequence,
        clip_id=point.clip_id,
        controller=point.controller,
        value=point.value,
        curve=point.curve,
        pitch_bend_range=point.pitch_bend_range,
        synthetic_reset=point.synthetic_reset,
    )


def _controller_sort_key(point: CompiledControllerEvent) -> tuple[float, int, int]:
    return (
        point.beat,
        _CONTROLLER_RESET_ORDER if point.synthetic_reset else _CONTROLLER_ORDER,
        point.sequence,
    )


def _event_sort_key(event: MusicalEvent) -> tuple[int, int, int]:
    return event.frame, event.order, event.sequence


def _resample_controller(
    points: Sequence[CompiledControllerEvent], ticks_per_beat: int
) -> tuple[MidiControllerEvent, ...]:
    if not points:
        return ()
    ordered = sorted(points, key=_controller_sort_key)
    effective: list[tuple[int, CompiledControllerEvent]] = []
    for point in ordered:
        tick = max(0, round(point.beat * ticks_per_beat))
        if effective and effective[-1][0] == tick:
            effective[-1] = (tick, point)
        else:
            effective.append((tick, point))
    sampled: list[MidiControllerEvent] = []
    for index, (tick, point) in enumerate(effective):
        sampled.append(
            MidiControllerEvent(
                tick=tick,
                controller=point.controller,
                value=point.value,
                pitch_bend_range=point.pitch_bend_range,
                sequence=point.sequence,
            )
        )
        if index + 1 == len(effective):
            continue
        next_tick, next_point = effective[index + 1]
        if next_tick <= tick:
            continue
        step = max(1, MIDI_CONTROLLER_TICK_STEP)
        for sample_tick in range(tick + step, next_tick, step):
            fraction = (sample_tick - tick) / (next_tick - tick)
            value = (
                point.value
                if point.curve == "hold"
                else point.value + fraction * (next_point.value - point.value)
            )
            sampled.append(
                MidiControllerEvent(
                    tick=sample_tick,
                    controller=point.controller,
                    value=value,
                    pitch_bend_range=point.pitch_bend_range,
                    sequence=point.sequence,
                )
            )
    return tuple(sampled)


# Public compatibility alias for callers that prefer the event-stream wording.
compile_arrangement = compile_track_events


__all__ = [
    "CompiledClipBoundary",
    "CompiledControllerEvent",
    "CompiledNote",
    "CompiledTrackEvents",
    "MIDI_CONTROLLER_TICK_STEP",
    "MIDI_MODULATION_STEPS",
    "MIDI_PITCH_BEND_STEPS",
    "MidiControllerEvent",
    "MusicalEvent",
    "compile_arrangement",
    "compile_track_events",
]
