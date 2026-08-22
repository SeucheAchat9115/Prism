"""Make a small multi-track beat and render a preview without hardware."""

from __future__ import annotations

import numpy as np
import soundfile as sf
from _support import make_music_fixture, parse_output_dir, print_json

from vibesound.audio import OfflineRenderBackend
from vibesound.engine import TransportClock
from vibesound.rendering import RenderCommand, RenderRequest


def main() -> int:
    run_dir = parse_output_dir(
        "make-beat",
        "Generate a small multi-track VibeSound beat and render a preview.",
    )
    project_path, project, tracks, scenes, clips = make_music_fixture(run_dir)
    clock = TransportClock.from_transport(project.transport)
    bar = int(clock.frames_per_bar)
    output_path = run_dir / "beat-preview.wav"
    request = RenderRequest(
        bars=4,
        commands=(
            RenderCommand(frame=0, operation="launch_scene", scene_id=scenes["Intro"].id),
            RenderCommand(
                frame=bar,
                operation="stop_all",
            ),
            RenderCommand(
                frame=bar,
                operation="launch_scene",
                scene_id=scenes["Groove"].id,
            ),
            RenderCommand(
                frame=bar * 2,
                operation="stop_all",
            ),
            RenderCommand(
                frame=bar * 2,
                operation="launch_scene",
                scene_id=scenes["Breakdown"].id,
            ),
            RenderCommand(frame=bar * 4, operation="stop_all"),
        ),
    )
    metadata = OfflineRenderBackend().render_project(project_path, output_path, request)
    samples, sample_rate = sf.read(output_path, always_2d=True, dtype="float32")
    print_json(
        {
            "project_path": str(project_path),
            "output_path": str(output_path),
            "tempo_bpm": project.transport.tempo_bpm,
            "tracks": list(tracks),
            "scenes": list(scenes),
            "clip_count": len(clips),
            "sample_rate": sample_rate,
            "channels": int(samples.shape[1]),
            "frames": int(samples.shape[0]),
            "peak": float(np.abs(samples).max()),
            "duration_seconds": metadata.duration_seconds,
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
