from __future__ import annotations

import numpy as np

from vibesound.rendering.sources import prepare_archive_project, resample_linear

from ._helpers import make_archive_project


def test_linear_resampling_is_deterministic_and_clamps_the_final_frame() -> None:
    source = np.asarray([[0.0], [1.0], [2.0]], dtype=np.float32)

    first = resample_linear(source, 4, 8)
    second = resample_linear(source, 4, 8)

    expected = np.asarray(
        [[0.0], [0.5], [1.0], [1.5], [2.0], [2.0]],
        dtype=np.float32,
    )
    np.testing.assert_array_equal(first, expected)
    np.testing.assert_array_equal(first, second)
    assert first.shape == (6, 1)


def test_same_rate_resampling_preserves_samples() -> None:
    source = np.asarray([[0.1, -0.2], [0.3, 0.4]], dtype=np.float32)

    result = resample_linear(source, 8, 8)

    np.testing.assert_array_equal(result, source)
    assert result is not source


def test_archive_preparation_resamples_assets_and_clip_regions(tmp_path) -> None:
    project_path, project, _, _, clip = make_archive_project(
        tmp_path,
        np.asarray([0.0, 1.0, 2.0], dtype=np.float32),
        source_rate=4,
        project_rate=8,
        source_offset_frames=1,
        duration_frames=1,
    )

    prepared = prepare_archive_project(project_path, project)
    runtime_asset = prepared.project.assets[0]
    runtime_clip = prepared.project.clips[0]

    assert runtime_asset.sample_rate == 8
    assert runtime_asset.frames == 6
    assert runtime_clip.id == clip.id
    assert runtime_clip.source_offset_frames == 2
    assert runtime_clip.duration_frames == 2
    assert prepared.project.transport.quantization == "none"
