"""Render an eight-bar scene arrangement and verify deterministic output."""

from __future__ import annotations

import hashlib

import soundfile as sf
from _support import make_music_fixture, parse_output_dir, print_json

from prism.audio import OfflineRenderBackend
from prism.engine import TransportClock
from prism.rendering import RenderCommand, RenderRequest


def main() -> int:
    run_dir = parse_output_dir(
        "render-song",
        "Render a scheduled scene arrangement without an audio device.",
    )
    project_path, project, _, scenes, _ = make_music_fixture(run_dir)
    clock = TransportClock.from_transport(project.transport)
    bar = int(clock.frames_per_bar)
    output_path = run_dir / "song.wav"
    request = RenderRequest(
        bars=8,
        commands=(
            RenderCommand(frame=0, operation="launch_scene", scene_id=scenes["Intro"].id),
            RenderCommand(frame=bar, operation="stop_all"),
            RenderCommand(
                frame=bar,
                operation="launch_scene",
                scene_id=scenes["Groove"].id,
            ),
            RenderCommand(frame=bar * 4, operation="stop_all"),
            RenderCommand(
                frame=bar * 4,
                operation="launch_scene",
                scene_id=scenes["Breakdown"].id,
            ),
            RenderCommand(frame=bar * 6, operation="stop_all"),
            RenderCommand(
                frame=bar * 6,
                operation="launch_scene",
                scene_id=scenes["Outro"].id,
            ),
            RenderCommand(frame=bar * 8, operation="stop_all"),
        ),
    )
    backend = OfflineRenderBackend()
    metadata = backend.render_project(project_path, output_path, request)
    second_path = run_dir / "song-second-render.wav"
    backend.render_project(project_path, second_path, request)
    info = sf.info(output_path)
    print_json(
        {
            "project_path": str(project_path),
            "output_path": str(output_path),
            "second_output_path": str(second_path),
            "format": metadata.format,
            "subtype": metadata.subtype,
            "sample_rate": info.samplerate,
            "channels": info.channels,
            "frames": info.frames,
            "duration_seconds": metadata.duration_seconds,
            "sha256": hashlib.sha256(output_path.read_bytes()).hexdigest(),
            "byte_identical_rerender": output_path.read_bytes() == second_path.read_bytes(),
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
