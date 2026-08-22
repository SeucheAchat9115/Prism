from __future__ import annotations

import hashlib
from uuid import uuid4

import numpy as np
import pytest

from vibesound.engine import (
    ClipLaunchedEvent,
    ClipStoppedEvent,
    SessionEngine,
    TransportChangedEvent,
    TransportMode,
)
from vibesound.engine.errors import (
    EngineValidationError,
    InvalidEngineCommandError,
    MissingAudioSourceError,
)
from vibesound.engine.sources import AudioBuffer, InMemoryClipSourceProvider
from vibesound.project.models import (
    AssetReference,
    AudioClip,
    ClipSlot,
    MixerState,
    Scene,
    Track,
)

from ._helpers import make_project


def _add_clip(
    project,
    provider_buffers: dict,
    *,
    track: Track,
    scene: Scene,
    values: list[float],
    name: str,
) -> AudioClip:
    asset_id = uuid4()
    clip = AudioClip(id=uuid4(), name=name, asset_id=asset_id)
    array = np.asarray(values, dtype=np.float32)[:, None]
    payload = array.tobytes()
    project.assets.append(
        AssetReference(
            id=asset_id,
            member_path=f"assets/audio/{asset_id}.wav",
            original_name=f"{name}.wav",
            size_bytes=len(payload),
            sha256=hashlib.sha256(payload).hexdigest(),
            sample_rate=project.transport.sample_rate,
            channels=1,
            frames=len(values),
            format="WAV",
        )
    )
    project.clips.append(clip)
    project.clip_slots.append(ClipSlot(track_id=track.id, scene_id=scene.id, clip_id=clip.id))
    provider_buffers[asset_id] = AudioBuffer(project.transport.sample_rate, array)
    return clip


def test_engine_launches_and_naturally_stops_a_clip() -> None:
    values = np.arange(1, 5, dtype=np.float32)
    project, provider, track, scene, _ = make_project(values)
    engine = SessionEngine(project, provider)

    action = engine.launch_slot(track.id, scene.id)
    assert action.target_frame == 0
    assert action.changed

    engine.play()
    first = engine.advance(2)
    second = engine.advance(2)

    assert first.start_frame == 0
    assert first.end_frame == 2
    assert [event.kind for event in first.events] == [
        "transport.changed",
        "clip.launched",
    ]
    assert isinstance(first.events[0], TransportChangedEvent)
    assert isinstance(first.events[1], ClipLaunchedEvent)
    np.testing.assert_allclose(first.samples[:, 0], values[:2] / np.sqrt(2.0))
    np.testing.assert_allclose(first.samples[:, 1], values[:2] / np.sqrt(2.0))
    assert [event.kind for event in second.events] == ["clip.stopped"]
    assert isinstance(second.events[0], ClipStoppedEvent)
    assert second.events[0].frame == 4
    assert engine.snapshot().active_clip_ids == ()


def test_scene_launch_is_quantized_and_empty_slot_is_a_no_op() -> None:
    values = np.ones(32, dtype=np.float32)
    project, provider, track, scene, _ = make_project(values, quantization="bar")
    empty_scene = Scene(name="Empty")
    project.scenes.append(empty_scene)
    engine = SessionEngine(project, provider)
    engine.play()
    engine.advance(1)

    empty = engine.launch_slot(track.id, empty_scene.id)
    action = engine.launch_scene(scene.id)
    step = engine.advance(15)

    assert not empty.changed
    assert action.target_frame == 16
    assert action.affected_track_ids == (track.id,)
    assert any(
        isinstance(event, ClipLaunchedEvent) and event.frame == 16 for event in step.events
    )
    assert np.all(step.samples == 0)
    assert engine.snapshot().position_frame == 16


def test_replacing_a_track_clip_stops_before_launching_the_replacement() -> None:
    first_values = [1.0] * 8
    second_values = [2.0] * 8
    project, _, track, first_scene, first_clip = make_project(
        np.asarray(first_values, dtype=np.float32), quantization="none"
    )
    second_scene = Scene(name="Second")
    project.scenes.append(second_scene)
    provider_buffers = {
        first_clip.asset_id: AudioBuffer(
            project.transport.sample_rate, np.asarray(first_values, dtype=np.float32)[:, None]
        )
    }
    second_clip = _add_clip(
        project,
        provider_buffers,
        track=track,
        scene=second_scene,
        values=second_values,
        name="Second clip",
    )
    engine = SessionEngine(project, InMemoryClipSourceProvider(provider_buffers))
    engine.launch_slot(track.id, first_scene.id)
    engine.play()
    engine.advance(1)
    engine.launch_slot(track.id, second_scene.id)

    step = engine.advance(1)

    assert [event.kind for event in step.events] == ["clip.stopped", "clip.launched"]
    assert step.events[0].clip_id == first_clip.id
    assert step.events[1].clip_id == second_clip.id
    np.testing.assert_allclose(step.samples, np.full((1, 2), 2.0 / np.sqrt(2.0)))


def test_mid_block_launch_is_split_at_the_exact_frame() -> None:
    values = np.ones(8, dtype=np.float32)
    project, provider, track, scene, _ = make_project(
        values,
        quantization="beat",
    )
    engine = SessionEngine(project, provider)
    engine.play()
    engine.advance(1)
    action = engine.launch_slot(track.id, scene.id)

    step = engine.advance(5)

    assert action.target_frame == 4
    assert [event.kind for event in step.events] == ["clip.launched"]
    assert step.events[0].frame == 4
    assert np.all(step.samples[:3] == 0)
    np.testing.assert_allclose(step.samples[3:], np.full((2, 2), 1.0 / np.sqrt(2.0)))


def test_looping_clip_honors_source_offset_and_duration() -> None:
    values = np.asarray([1, 2, 3, 4], dtype=np.float32)
    project, provider, track, scene, _ = make_project(
        values,
        source_offset_frames=1,
        duration_frames=5,
        loop=True,
    )
    engine = SessionEngine(project, provider)
    engine.launch_slot(track.id, scene.id)
    engine.play()

    step = engine.advance(5)

    expected = np.asarray([2, 3, 4, 2, 3], dtype=np.float32) / np.sqrt(2.0)
    np.testing.assert_allclose(step.samples[:, 0], expected)
    assert [event.kind for event in step.events] == [
        "transport.changed",
        "clip.launched",
        "clip.stopped",
    ]
    assert step.events[-1].frame == 5


def test_pause_stop_and_reset_have_daw_style_position_behavior() -> None:
    project, provider, track, scene, _ = make_project(np.ones(8, dtype=np.float32))
    engine = SessionEngine(project, provider)
    engine.launch_slot(track.id, scene.id)
    engine.play()
    engine.advance(1)

    engine.pause()
    paused = engine.advance(3)
    assert paused.start_frame == paused.end_frame == 1
    assert engine.snapshot().mode == TransportMode.PAUSED
    assert engine.snapshot().position_frame == 1
    assert np.all(paused.samples == 0)

    engine.stop()
    stopped = engine.advance(0)
    assert engine.snapshot().mode == TransportMode.STOPPED
    assert engine.snapshot().active_clip_ids == ()
    assert [event.kind for event in stopped.events] == [
        "transport.changed",
        "clip.stopped",
    ]

    engine.reset()
    engine.advance(0)
    assert engine.snapshot().position_frame == 0
    assert engine.snapshot().mode == TransportMode.STOPPED


def test_block_size_does_not_change_output_or_events() -> None:
    values = np.arange(1, 9, dtype=np.float32)
    project, provider, track, scene, _ = make_project(values, quantization="none")
    first = SessionEngine(project, provider)
    second = SessionEngine(project, provider)
    first.launch_slot(track.id, scene.id)
    second.launch_slot(track.id, scene.id)
    first.play()
    second.play()

    one_block = first.advance(8)
    many_blocks = [second.advance(size) for size in (2, 3, 3)]
    many_samples = np.concatenate([step.samples for step in many_blocks], axis=0)
    many_events = [event for step in many_blocks for event in step.events]

    np.testing.assert_array_equal(one_block.samples, many_samples)
    assert [event.kind for event in one_block.events] == [event.kind for event in many_events]
    assert [event.frame for event in one_block.events] == [event.frame for event in many_events]
    assert first.snapshot() == second.snapshot()


def test_engine_rejects_missing_sources_and_invalid_clip_regions() -> None:
    values = np.ones(4, dtype=np.float32)
    project, _, track, scene, _ = make_project(values)

    with pytest.raises(MissingAudioSourceError):
        SessionEngine(project, InMemoryClipSourceProvider({}))

    invalid_project, provider, _, _, _ = make_project(values, source_offset_frames=4)
    with pytest.raises(EngineValidationError, match="starts beyond"):
        SessionEngine(invalid_project, provider)


def test_engine_rejects_non_matching_source_sample_rate() -> None:
    values = np.ones(4, dtype=np.float32)
    project, _, _, _, clip = make_project(values)
    source = AudioBuffer(16, values[:, None])

    with pytest.raises(EngineValidationError, match="sample rate"):
        SessionEngine(project, InMemoryClipSourceProvider({clip.asset_id: source}))


def test_mixer_applies_gain_and_preserves_float_headroom() -> None:
    track = Track(name="Loud", mixer=MixerState(gain_db=6.0, pan=-1.0))
    project, provider, track, scene, _ = make_project(
        np.full(4, 2.0, dtype=np.float32),
        track=track,
    )
    engine = SessionEngine(project, provider)
    engine.launch_slot(track.id, scene.id)
    engine.play()

    step = engine.advance(1)

    expected = 2.0 * 10.0 ** (6.0 / 20.0)
    assert step.samples[0, 0] == pytest.approx(expected)
    assert step.samples[0, 1] == pytest.approx(0.0)
    assert step.samples[0, 0] > 1.0


def test_mixer_preserves_stereo_sources_with_balance_pan() -> None:
    track = Track(name="Stereo", mixer=MixerState(pan=-1.0))
    samples = np.asarray([[1.0, 2.0], [3.0, 4.0]], dtype=np.float32)
    project, provider, track, scene, _ = make_project(samples, track=track)
    engine = SessionEngine(project, provider)
    engine.launch_slot(track.id, scene.id)
    engine.play()

    step = engine.advance(2)

    np.testing.assert_array_equal(step.samples, np.asarray([[1, 0], [3, 0]], dtype=np.float32))


def test_mixer_mute_and_solo_rules() -> None:
    first_values = np.ones(4, dtype=np.float32)
    project, _, first_track, scene, first_clip = make_project(first_values)
    second_track = Track(name="Solo", order=1, mixer=MixerState(solo=True))
    project.tracks.append(second_track)
    buffers = {
        first_clip.asset_id: AudioBuffer(
            project.transport.sample_rate, first_values[:, None]
        )
    }
    _add_clip(
        project,
        buffers,
        track=second_track,
        scene=scene,
        values=[2.0] * 4,
        name="Solo clip",
    )
    engine = SessionEngine(project, InMemoryClipSourceProvider(buffers))
    engine.launch_scene(scene.id)
    engine.play()

    solo_step = engine.advance(1)

    np.testing.assert_allclose(solo_step.samples, np.full((1, 2), 2.0 / np.sqrt(2.0)))

    muted_project = project.model_copy(deep=True)
    muted_project.tracks[1].mixer.muted = True
    muted_engine = SessionEngine(muted_project, InMemoryClipSourceProvider(buffers))
    muted_engine.launch_scene(scene.id)
    muted_engine.play()

    muted_step = muted_engine.advance(1)

    np.testing.assert_array_equal(muted_step.samples, np.zeros((1, 2), dtype=np.float32))


def test_stop_all_clears_active_tracks_at_one_boundary() -> None:
    values = np.ones(8, dtype=np.float32)
    project, _, first_track, scene, first_clip = make_project(values)
    second_track = Track(name="Second", order=1)
    project.tracks.append(second_track)
    buffers = {
        first_clip.asset_id: AudioBuffer(project.transport.sample_rate, values[:, None])
    }
    _add_clip(
        project,
        buffers,
        track=second_track,
        scene=scene,
        values=[2.0] * 8,
        name="Second clip",
    )
    engine = SessionEngine(project, InMemoryClipSourceProvider(buffers))
    engine.launch_scene(scene.id)
    engine.play()
    engine.advance(1)

    action = engine.stop_all()
    step = engine.advance(0)

    assert action.affected_track_ids == (first_track.id, second_track.id)
    assert [event.kind for event in step.events] == ["clip.stopped", "clip.stopped"]
    assert engine.snapshot().active_clip_ids == ()


def test_advance_rejects_negative_and_boolean_frame_counts() -> None:
    project, provider, _, _, _ = make_project(np.ones(4, dtype=np.float32))
    engine = SessionEngine(project, provider)

    with pytest.raises(InvalidEngineCommandError):
        engine.advance(-1)
    with pytest.raises(InvalidEngineCommandError):
        engine.advance(True)
