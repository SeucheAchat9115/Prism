"""Render a self-contained project archive to a deterministic float WAV."""

from __future__ import annotations

import soundfile as sf
from _support import make_archive_fixture, parse_output_dir, print_json

from vibesound.audio import OfflineRenderBackend
from vibesound.rendering import RenderCommand, RenderRequest


def main() -> int:
    run_dir = parse_output_dir(
        "offline-render",
        "Render a .vibesound archive without an audio device.",
    )
    project_path, project, _, scene, _ = make_archive_fixture(
        run_dir,
        sample_rate=8000,
        seconds=1.0,
        loop=True,
    )
    output_path = run_dir / "render.wav"
    stop_frame = int(1.25 * project.transport.sample_rate)
    request = RenderRequest(
        seconds=2.0,
        commands=(
            RenderCommand(frame=0, operation="launch_scene", scene_id=scene.id),
            RenderCommand(frame=stop_frame, operation="stop_all"),
        ),
    )
    metadata = OfflineRenderBackend().render_project(project_path, output_path, request)
    info = sf.info(output_path)
    print_json(
        {
            "project_path": str(project_path),
            "output_path": str(output_path),
            "format": metadata.format,
            "subtype": metadata.subtype,
            "sample_rate": info.samplerate,
            "channels": info.channels,
            "frames": info.frames,
            "duration_seconds": metadata.duration_seconds,
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
