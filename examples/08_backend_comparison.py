"""Compare fake playback and offline rendering without opening a device."""

from __future__ import annotations

import numpy as np
from _support import (
    action_summary,
    event_summary,
    make_memory_fixture,
    parse_output_dir,
    print_json,
)

from vibesound.audio import FakeAudioBackend, OfflineRenderBackend
from vibesound.rendering import RenderCommand, RenderRequest


def main() -> int:
    run_dir = parse_output_dir(
        "backend-comparison",
        "Compare the fake playback and offline render backend contracts.",
    )
    project, provider, track, scene, _ = make_memory_fixture(
        sample_rate=8000,
        quantization="none",
        loop=True,
    )
    with FakeAudioBackend(project, provider) as backend:
        launch = backend.launch_slot(track.id, scene.id)
        backend.start()
        playing = backend.advance(1024)
        backend.pause()
        paused = backend.advance(256)
        paused_snapshot = backend.snapshot()
        backend.reset()
        reset_snapshot = backend.snapshot()

    output_path = run_dir / "offline.wav"
    request = RenderRequest(
        seconds=1.0,
        commands=(
            RenderCommand(
                frame=0,
                operation="launch_slot",
                track_id=track.id,
                scene_id=scene.id,
            ),
        ),
    )
    metadata = OfflineRenderBackend().render(project, provider, output_path, request)
    print_json(
        {
            "fake_backend": {
                "launch": action_summary(launch),
                "playing_frames": [playing.start_frame, playing.end_frame],
                "playing_peak": float(np.abs(playing.samples).max()),
                "playing_events": event_summary(playing.events),
                "paused_state": paused_snapshot.state.value,
                "paused_silent": bool(np.abs(paused.samples).max() == 0.0),
                "reset_state": reset_snapshot.state.value,
                "reset_position_frame": reset_snapshot.engine_snapshot.position_frame,
            },
            "offline_backend": {
                "output_path": str(metadata.output_path),
                "sample_rate": metadata.sample_rate,
                "channels": metadata.channels,
                "frames": metadata.frames,
                "duration_seconds": metadata.duration_seconds,
            },
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
