from __future__ import annotations

import hashlib
from zipfile import ZipFile

import numpy as np
import pytest
import soundfile as sf

from vibesound.project import load_project, save_project, validate_project
from vibesound.project.models import AudioClip, ClipSlot, Scene
from vibesound.rendering import (
    InvalidRenderRequestError,
    RenderCommand,
    RenderRequest,
    RenderValidationError,
    render,
    render_project,
)
from vibesound.rendering.errors import RenderOutputError

from ._helpers import make_archive_project, make_memory_project


def _read_float_wav(path):
    samples, sample_rate = sf.read(path, dtype="float32", always_2d=True)
    return samples, sample_rate


def test_render_uses_exact_command_frames_even_when_project_is_quantized(tmp_path) -> None:
    project, provider, track, scene, _ = make_memory_project(
        np.ones(32, dtype=np.float32), quantization="bar"
    )
    output = tmp_path / "exact.wav"
    request = RenderRequest(
        seconds=1.0,
        commands=(
            RenderCommand(frame=1, operation="launch_slot", track_id=track.id, scene_id=scene.id),
            RenderCommand(frame=4, operation="stop_track", track_id=track.id),
            RenderCommand(frame=8, operation="stop_all"),
        ),
    )

    metadata = render(project, provider, output, request)
    samples, sample_rate = _read_float_wav(output)

    assert metadata.frames == 8
    assert metadata.duration_seconds == 1.0
    assert sample_rate == 8
    np.testing.assert_allclose(
        samples[:, 0],
        np.asarray([0.0, 1.0, 1.0, 1.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float32) / np.sqrt(2.0),
    )


def test_render_commands_preserve_same_frame_order_and_support_scenes(tmp_path) -> None:
    project, provider, track, first_scene, first_clip = make_memory_project(
        np.ones(16, dtype=np.float32), quantization="none"
    )
    second_scene = Scene(name="Second", order=1)
    second_clip = AudioClip(name="Second clip", asset_id=first_clip.asset_id)
    second_asset_id = second_clip.asset_id
    second_clip.asset_id = first_clip.asset_id
    del second_asset_id
    project.scenes.append(second_scene)
    project.clips.append(second_clip)
    project.clip_slots.append(
        ClipSlot(track_id=track.id, scene_id=second_scene.id, clip_id=second_clip.id)
    )
    # The same source is enough to prove same-frame replacement ordering.
    output = tmp_path / "same-frame.wav"
    request = RenderRequest(
        seconds=1.0,
        commands=(
            RenderCommand(
                frame=0,
                operation="launch_slot",
                track_id=track.id,
                scene_id=first_scene.id,
            ),
            RenderCommand(
                frame=0,
                operation="launch_slot",
                track_id=track.id,
                scene_id=second_scene.id,
            ),
            RenderCommand(frame=3, operation="stop_all"),
        ),
    )

    metadata = render(project, provider, output, request)

    samples, _ = _read_float_wav(output)
    assert metadata.channels == 2
    assert np.all(samples[:3, 0] > 0)
    np.testing.assert_array_equal(samples[3:], np.zeros((5, 2), dtype=np.float32))


def test_render_without_commands_is_silence(tmp_path) -> None:
    project, provider, _, _, _ = make_memory_project(np.ones(8, dtype=np.float32))

    output = tmp_path / "silence.wav"
    metadata = render(project, provider, output, RenderRequest(seconds=1.5))
    samples, sample_rate = _read_float_wav(output)

    assert metadata.frames == 12
    assert sample_rate == project.transport.sample_rate
    np.testing.assert_array_equal(samples, np.zeros((12, 2), dtype=np.float32))


def test_bars_and_seconds_round_up_to_project_frames(tmp_path) -> None:
    project, provider, _, _, _ = make_memory_project(np.ones(32, dtype=np.float32))

    bars_output = tmp_path / "bars.wav"
    seconds_output = tmp_path / "seconds.wav"
    bars = render(project, provider, bars_output, RenderRequest(bars=1))
    seconds = render(project, provider, seconds_output, RenderRequest(seconds=0.51))

    assert bars.frames == 16
    assert seconds.frames == 5


def test_wav_metadata_and_repeated_render_bytes_are_stable(tmp_path) -> None:
    project, provider, track, scene, _ = make_memory_project(np.ones(20, dtype=np.float32))
    request = RenderRequest(
        seconds=1.0,
        commands=(RenderCommand(0, "launch_slot", track.id, scene.id),),
    )
    first_output = tmp_path / "first.wav"
    second_output = tmp_path / "second.wav"

    first = render(project, provider, first_output, request)
    second = render(project, provider, second_output, request)

    assert first.format == "WAV"
    assert first.subtype == "FLOAT"
    assert first.channels == 2
    assert sf.info(first_output).subtype == "FLOAT"
    assert first_output.read_bytes() == second_output.read_bytes()
    assert first.project_id == second.project_id == project.project_id
    assert first.revision == second.revision == project.revision.number


def test_archive_render_validates_and_embeds_source_audio(tmp_path) -> None:
    project_path, project, track, scene, _ = make_archive_project(
        tmp_path, np.ones(8, dtype=np.float32), source_rate=8, project_rate=8
    )
    output = tmp_path / "archive.wav"

    metadata = render_project(
        project_path,
        output,
        RenderRequest(
            seconds=1.0,
            commands=(RenderCommand(0, "launch_scene", scene_id=scene.id),),
        ),
    )
    samples, sample_rate = _read_float_wav(output)

    assert validate_project(project_path).ok
    assert metadata.project_id == project.project_id
    assert metadata.sample_rate == sample_rate == 8
    assert samples.shape == (8, 2)
    np.testing.assert_allclose(samples[:8], np.ones((8, 2), dtype=np.float32) / np.sqrt(2.0))
    assert track.id in {item.id for item in project.tracks}


def test_archive_render_rejects_corrupt_assets_before_touching_existing_output(tmp_path) -> None:
    project_path, _, _, _, _ = make_archive_project(
        tmp_path, np.ones(8, dtype=np.float32), source_rate=8, project_rate=8
    )
    corrupt_path = tmp_path / "corrupt.vibesound"
    with ZipFile(project_path, "r") as source, ZipFile(corrupt_path, "w") as target:
        for name in source.namelist():
            payload = source.read(name)
            if name.startswith("assets/audio/"):
                payload = b"corrupt"
            target.writestr(name, payload)
    output = tmp_path / "existing.wav"
    sentinel = b"keep this output"
    output.write_bytes(sentinel)

    with pytest.raises(RenderValidationError):
        render_project(corrupt_path, output, RenderRequest(seconds=1.0))

    assert output.read_bytes() == sentinel
    assert not list(tmp_path.glob(f".{output.name}.*.tmp"))


def test_archive_render_rejects_manifest_format_mismatch(tmp_path) -> None:
    project_path, project, _, _, _ = make_archive_project(
        tmp_path, np.ones(4, dtype=np.float32), source_rate=8, project_rate=8
    )
    invalid = load_project(project_path)
    invalid.assets[0].format = "FLAC"
    save_project(project_path, invalid)

    with pytest.raises(RenderValidationError, match="format mismatch"):
        render_project(project_path, tmp_path / "unsupported.wav", RenderRequest(seconds=1.0))


def test_archive_render_does_not_overwrite_source_project(tmp_path) -> None:
    project_path, _, _, _, _ = make_archive_project(
        tmp_path, np.ones(4, dtype=np.float32), source_rate=8, project_rate=8
    )
    original = project_path.read_bytes()

    with pytest.raises(RenderValidationError, match="must not overwrite"):
        render_project(project_path, project_path, RenderRequest(seconds=1.0))

    assert project_path.read_bytes() == original


def test_output_validation_and_invalid_command_leave_existing_output_untouched(tmp_path) -> None:
    project, provider, track, scene, _ = make_memory_project(np.ones(8, dtype=np.float32))
    output = tmp_path / "existing.wav"
    sentinel = hashlib.sha256(b"existing").digest()
    output.write_bytes(sentinel)

    with pytest.raises(InvalidRenderRequestError):
        render(
            project,
            provider,
            output,
            RenderRequest(
                seconds=1.0,
                commands=(
                    RenderCommand(9, "launch_slot", track.id, scene.id),
                ),
            ),
        )
    assert output.read_bytes() == sentinel

    with pytest.raises(RenderOutputError):
        render(project, provider, tmp_path, RenderRequest(seconds=1.0))
