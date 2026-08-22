"""Deterministic session scheduling, clip playback, and mixing."""

from __future__ import annotations

from dataclasses import dataclass
from math import cos, pi, sin
from typing import Literal
from uuid import UUID

import numpy as np

from vibesound.engine.clock import TransportClock
from vibesound.engine.errors import (
    EngineValidationError,
    InvalidEngineCommandError,
    MissingAudioSourceError,
)
from vibesound.engine.sources import AudioBuffer, ClipSourceProvider
from vibesound.engine.types import (
    ClipLaunchedEvent,
    ClipStoppedEvent,
    EngineEvent,
    EngineSnapshot,
    EngineStep,
    ScheduledAction,
    TransportChangedEvent,
    TransportMode,
    empty_stereo_buffer,
)
from vibesound.project.models import AudioClip, Project, Scene, Track
from vibesound.project.validation import project_reference_issues


@dataclass(frozen=True, slots=True)
class _PendingAction:
    frame: int
    track_id: UUID
    kind: Literal["launch", "stop"]
    scene_id: UUID | None = None
    clip_id: UUID | None = None


@dataclass(frozen=True, slots=True)
class _ActiveClip:
    track_id: UUID
    scene_id: UUID
    clip_id: UUID
    clip: AudioClip
    source: AudioBuffer
    launch_frame: int


class SessionEngine:
    """A thread-free, sample-frame deterministic session engine."""

    def __init__(self, project: Project, sources: ClipSourceProvider) -> None:
        issues = project_reference_issues(project)
        if issues:
            messages = "; ".join(f"{issue.path}: {issue.message}" for issue in issues)
            raise EngineValidationError(f"Project cannot initialize the engine: {messages}")

        self._project = project.model_copy(deep=True)
        self._clock = TransportClock.from_transport(self._project.transport)
        self._mode = TransportMode.STOPPED
        self._position_frame = 0
        self._pending: dict[tuple[int, UUID], _PendingAction] = {}
        self._active: dict[UUID, _ActiveClip] = {}
        self._queued_events: list[EngineEvent] = []
        self._track_by_id = {track.id: track for track in self._project.tracks}
        self._scene_by_id = {scene.id: scene for scene in self._project.scenes}
        self._clip_by_id = {clip.id: clip for clip in self._project.clips}
        self._slot_by_pair = {
            (slot.track_id, slot.scene_id): slot for slot in self._project.clip_slots
        }
        self._track_order = tuple(
            sorted(self._project.tracks, key=lambda track: (track.order, str(track.id)))
        )
        self._buffers = self._load_referenced_sources(sources)

    @property
    def project(self) -> Project:
        """Return a defensive project snapshot used by this engine."""

        return self._project.model_copy(deep=True)

    @property
    def clock(self) -> TransportClock:
        """Return the immutable timing configuration."""

        return self._clock

    def snapshot(self) -> EngineSnapshot:
        """Return current runtime state without exposing mutable engine internals."""

        active = tuple(
            (track_id, self._active[track_id].clip_id)
            for track_id in sorted(self._active, key=self._track_sort_key)
        )
        pending_frames = tuple(sorted({frame for frame, _ in self._pending}))
        return EngineSnapshot(
            mode=self._mode,
            position_frame=self._position_frame,
            active_clip_ids=active,
            pending_action_frames=pending_frames,
        )

    def play(self) -> None:
        """Resume transport from its current frame."""

        if self._mode == TransportMode.PLAYING:
            return
        self._mode = TransportMode.PLAYING
        self._queue_transport_event()

    def pause(self) -> None:
        """Pause transport without clearing active clips or pending actions."""

        if self._mode == TransportMode.PAUSED:
            return
        self._mode = TransportMode.PAUSED
        self._queue_transport_event()

    def stop(self) -> None:
        """Stop immediately, clear active clips, and cancel session actions."""

        if self._mode == TransportMode.STOPPED and not self._active and not self._pending:
            return
        self._pending.clear()
        for track_id in tuple(sorted(self._active, key=self._track_sort_key)):
            self._stop_active(track_id, self._position_frame)
        self._mode = TransportMode.STOPPED
        self._queue_transport_event()

    def reset(self) -> None:
        """Stop playback and move the timeline position to frame zero."""

        self._pending.clear()
        for track_id in tuple(sorted(self._active, key=self._track_sort_key)):
            active = self._active.pop(track_id)
            self._queued_events.append(
                ClipStoppedEvent(
                    frame=0,
                    track_id=active.track_id,
                    scene_id=active.scene_id,
                    clip_id=active.clip_id,
                )
            )
        self._position_frame = 0
        self._mode = TransportMode.STOPPED
        self._queued_events.append(
            TransportChangedEvent(
                frame=0,
                mode=self._mode,
                position_frame=0,
            )
        )

    def launch_slot(self, track_id: UUID, scene_id: UUID) -> ScheduledAction:
        """Launch the clip in a track/scene slot at the quantized target frame."""

        self._require_track(track_id)
        self._require_scene(scene_id)
        target_frame = self._clock.quantize(self._position_frame)
        slot = self._slot_by_pair.get((track_id, scene_id))
        if slot is None or slot.clip_id is None:
            return ScheduledAction(target_frame, (), False)
        clip = self._clip_by_id[slot.clip_id]
        current = self._active.get(track_id)
        if current is not None and current.clip_id == clip.id and not any(
            key[1] == track_id for key in self._pending
        ):
            return ScheduledAction(target_frame, (), False)
        action = _PendingAction(
            frame=target_frame,
            track_id=track_id,
            kind="launch",
            scene_id=scene_id,
            clip_id=clip.id,
        )
        changed = self._replace_pending_for_track(track_id, action)
        return ScheduledAction(target_frame, (track_id,), changed)

    def launch_scene(self, scene_id: UUID) -> ScheduledAction:
        """Launch all non-empty slots in a scene at one shared target frame."""

        self._require_scene(scene_id)
        target_frame = self._clock.quantize(self._position_frame)
        affected: list[UUID] = []
        changed = False
        for track in self._track_order:
            slot = self._slot_by_pair.get((track.id, scene_id))
            if slot is None or slot.clip_id is None:
                continue
            action = _PendingAction(
                frame=target_frame,
                track_id=track.id,
                kind="launch",
                scene_id=scene_id,
                clip_id=slot.clip_id,
            )
            changed = self._replace_pending_for_track(track.id, action) or changed
            affected.append(track.id)
        return ScheduledAction(target_frame, tuple(affected), changed)

    def stop_track(self, track_id: UUID) -> ScheduledAction:
        """Stop one track at the current quantized target frame."""

        self._require_track(track_id)
        target_frame = self._clock.quantize(self._position_frame)
        had_pending = self._cancel_pending_for_track(track_id)
        if track_id not in self._active:
            return ScheduledAction(target_frame, (), had_pending)
        action = _PendingAction(frame=target_frame, track_id=track_id, kind="stop")
        changed = self._replace_pending_for_track(track_id, action) or had_pending
        return ScheduledAction(target_frame, (track_id,), changed)

    def stop_all(self) -> ScheduledAction:
        """Stop all active tracks at one shared quantized target frame."""

        target_frame = self._clock.quantize(self._position_frame)
        had_pending = bool(self._pending)
        self._pending.clear()
        affected: list[UUID] = []
        for track_id in sorted(self._active, key=self._track_sort_key):
            self._pending[(target_frame, track_id)] = _PendingAction(
                frame=target_frame,
                track_id=track_id,
                kind="stop",
            )
            affected.append(track_id)
        return ScheduledAction(target_frame, tuple(affected), bool(affected) or had_pending)

    def advance(self, frames: int) -> EngineStep:
        """Advance the engine by an exact number of frames and return its output."""

        if not isinstance(frames, int) or isinstance(frames, bool) or frames < 0:
            raise InvalidEngineCommandError("advance() frames must be a non-negative integer")

        start_frame = self._position_frame
        if self._mode != TransportMode.PLAYING:
            self._apply_boundary(start_frame)
            return EngineStep(
                start_frame=start_frame,
                end_frame=start_frame,
                samples=empty_stereo_buffer(frames),
                events=self._take_events(),
            )

        end_frame = start_frame + frames
        output = np.zeros((frames, 2), dtype=np.float64)
        cursor = start_frame
        while True:
            self._apply_boundary(cursor)
            if cursor >= end_frame:
                break
            next_frame = self._next_boundary(cursor, end_frame)
            if next_frame <= cursor:
                raise RuntimeError("Engine failed to advance beyond a scheduling boundary")
            output[cursor - start_frame : next_frame - start_frame] = self._render_range(
                cursor, next_frame
            )
            cursor = next_frame
        self._position_frame = end_frame
        return EngineStep(
            start_frame=start_frame,
            end_frame=end_frame,
            samples=output.astype(np.float32),
            events=self._take_events(),
        )

    def _load_referenced_sources(self, sources: ClipSourceProvider) -> dict[UUID, AudioBuffer]:
        referenced = {clip.asset_id for clip in self._project.clips}
        assets = {asset.id: asset for asset in self._project.assets}
        buffers: dict[UUID, AudioBuffer] = {}
        for asset_id in sorted(referenced, key=str):
            asset = assets[asset_id]
            try:
                buffer = sources.get(asset_id)
            except MissingAudioSourceError:
                raise
            except Exception as exc:
                raise MissingAudioSourceError(
                    f"Could not load audio source for asset {asset_id}: {exc}"
                ) from exc
            if not isinstance(buffer, AudioBuffer):
                raise EngineValidationError(
                    f"Audio source provider returned an invalid value for asset {asset_id}"
                )
            if buffer.sample_rate != self._project.transport.sample_rate:
                raise EngineValidationError(
                    f"Audio source {asset_id} has sample rate {buffer.sample_rate}; "
                    f"expected {self._project.transport.sample_rate}"
                )
            if buffer.samples.shape[0] != asset.frames:
                raise EngineValidationError(
                    f"Audio source {asset_id} has {buffer.samples.shape[0]} frames; "
                    f"manifest declares {asset.frames}"
                )
            if buffer.samples.shape[1] != asset.channels:
                raise EngineValidationError(
                    f"Audio source {asset_id} has {buffer.samples.shape[1]} channels; "
                    f"manifest declares {asset.channels}"
                )
            for clip in self._project.clips:
                if (
                    clip.asset_id == asset_id
                    and clip.source_offset_frames >= buffer.samples.shape[0]
                ):
                    raise EngineValidationError(
                        f"Clip {clip.id} starts beyond the end of audio source {asset_id}"
                    )
            buffers[asset_id] = buffer
        return buffers

    def _require_track(self, track_id: UUID) -> Track:
        try:
            return self._track_by_id[track_id]
        except KeyError as exc:
            raise InvalidEngineCommandError(f"Unknown track: {track_id}") from exc

    def _require_scene(self, scene_id: UUID) -> Scene:
        try:
            return self._scene_by_id[scene_id]
        except KeyError as exc:
            raise InvalidEngineCommandError(f"Unknown scene: {scene_id}") from exc

    def _track_sort_key(self, track_id: UUID) -> tuple[int, str]:
        track = self._track_by_id[track_id]
        return track.order, str(track.id)

    def _cancel_pending_for_track(self, track_id: UUID) -> bool:
        keys = [key for key in self._pending if key[1] == track_id]
        for key in keys:
            del self._pending[key]
        return bool(keys)

    def _replace_pending_for_track(self, track_id: UUID, action: _PendingAction) -> bool:
        existing = self._pending.get((action.frame, track_id))
        if existing == action:
            return False
        self._pending[(action.frame, track_id)] = action
        return True

    def _queue_transport_event(self) -> None:
        self._queued_events.append(
            TransportChangedEvent(
                frame=self._position_frame,
                mode=self._mode,
                position_frame=self._position_frame,
            )
        )

    def _stop_active(self, track_id: UUID, frame: int) -> None:
        active = self._active.pop(track_id, None)
        if active is None:
            return
        self._queued_events.append(
            ClipStoppedEvent(
                frame=frame,
                track_id=active.track_id,
                scene_id=active.scene_id,
                clip_id=active.clip_id,
            )
        )

    def _apply_boundary(self, frame: int) -> None:
        self._apply_natural_stops(frame)
        actions = [
            action
            for (action_frame, _), action in self._pending.items()
            if action_frame == frame
        ]
        for action in sorted(actions, key=lambda item: self._track_sort_key(item.track_id)):
            self._pending.pop((action.frame, action.track_id), None)
            if action.kind == "stop":
                self._stop_active(action.track_id, frame)
            else:
                self._launch_active(action, frame)

    def _apply_natural_stops(self, frame: int) -> None:
        for track_id in tuple(sorted(self._active, key=self._track_sort_key)):
            end_frame = self._active_end_frame(self._active[track_id])
            if end_frame is not None and end_frame <= frame:
                self._stop_active(track_id, end_frame)

    def _launch_active(self, action: _PendingAction, frame: int) -> None:
        if action.scene_id is None or action.clip_id is None:
            raise RuntimeError("Launch action is missing scene or clip IDs")
        clip = self._clip_by_id[action.clip_id]
        current = self._active.get(action.track_id)
        if current is not None:
            if current.clip_id == clip.id:
                return
            self._stop_active(action.track_id, frame)
        self._active[action.track_id] = _ActiveClip(
            track_id=action.track_id,
            scene_id=action.scene_id,
            clip_id=clip.id,
            clip=clip,
            source=self._buffers[clip.asset_id],
            launch_frame=frame,
        )
        self._queued_events.append(
            ClipLaunchedEvent(
                frame=frame,
                track_id=action.track_id,
                scene_id=action.scene_id,
                clip_id=clip.id,
            )
        )

    def _active_end_frame(self, active: _ActiveClip) -> int | None:
        clip = active.clip
        source_remaining = active.source.samples.shape[0] - clip.source_offset_frames
        if clip.loop and clip.duration_frames is None:
            return None
        requested_duration = clip.duration_frames or source_remaining
        duration = requested_duration if clip.loop else min(requested_duration, source_remaining)
        return active.launch_frame + duration

    def _next_boundary(self, cursor: int, end_frame: int) -> int:
        candidates = [end_frame]
        for action_frame, _ in self._pending:
            if cursor < action_frame <= end_frame:
                candidates.append(action_frame)
        for active in self._active.values():
            active_end = self._active_end_frame(active)
            if active_end is not None and cursor < active_end <= end_frame:
                candidates.append(active_end)
        return min(candidates)

    def _render_range(self, start_frame: int, end_frame: int) -> np.ndarray:
        length = end_frame - start_frame
        mixed = np.zeros((length, 2), dtype=np.float64)
        solo_ids = {track.id for track in self._track_order if track.mixer.solo}
        for track in self._track_order:
            active = self._active.get(track.id)
            if active is None or track.mixer.muted or (solo_ids and track.id not in solo_ids):
                continue
            source = self._clip_samples(active, start_frame, length)
            gain = 10.0 ** ((active.clip.gain_db + track.mixer.gain_db) / 20.0)
            if source.shape[1] == 1:
                angle = (track.mixer.pan + 1.0) * pi / 4.0
                mixed[:, 0] += source[:, 0].astype(np.float64) * gain * cos(angle)
                mixed[:, 1] += source[:, 0].astype(np.float64) * gain * sin(angle)
            else:
                left_gain, right_gain = self._stereo_balance(track.mixer.pan)
                mixed[:, 0] += source[:, 0].astype(np.float64) * gain * left_gain
                mixed[:, 1] += source[:, 1].astype(np.float64) * gain * right_gain
        return mixed

    @staticmethod
    def _stereo_balance(pan: float) -> tuple[float, float]:
        if pan < 0:
            return 1.0, 1.0 + pan
        return 1.0 - pan, 1.0

    def _clip_samples(self, active: _ActiveClip, start_frame: int, length: int) -> np.ndarray:
        local_start = start_frame - active.launch_frame
        source_tail = active.source.samples[active.clip.source_offset_frames :]
        if active.clip.loop:
            indexes = (np.arange(local_start, local_start + length) % source_tail.shape[0]).astype(
                np.intp
            )
            return active.source.samples[active.clip.source_offset_frames :][indexes]
        return source_tail[local_start : local_start + length]

    def _take_events(self) -> tuple[EngineEvent, ...]:
        events = self._queued_events
        self._queued_events = []
        return tuple(sorted(events, key=self._event_sort_key))

    def _event_sort_key(self, event: EngineEvent) -> tuple[int, int, tuple[int, str]]:
        if isinstance(event, TransportChangedEvent):
            return event.frame, 0, (-1, "")
        track_key = self._track_sort_key(event.track_id)
        priority = 1 if isinstance(event, ClipStoppedEvent) else 2
        return event.frame, priority, track_key
