"""Exercise the audio backend contract without opening a physical device."""

from __future__ import annotations

from _support import action_summary, event_summary, make_memory_fixture, print_json

from vibesound.audio import FakeAudioBackend


def main() -> int:
    project, provider, _, scene, _ = make_memory_fixture(
        sample_rate=8000,
        quantization="none",
        loop=True,
    )
    with FakeAudioBackend(project, provider) as backend:
        launch = backend.launch_scene(scene.id)
        backend.start()
        playing_step = backend.advance(1024)
        backend.pause()
        paused_step = backend.advance(256)
        paused_snapshot = backend.snapshot()
        backend.reset()
        reset_snapshot = backend.snapshot()

    print_json(
        {
            "launch": action_summary(launch),
            "playing": {
                "state": "running",
                "frames": [playing_step.start_frame, playing_step.end_frame],
                "peak": float(abs(playing_step.samples).max()),
                "events": event_summary(playing_step.events),
            },
            "paused": {
                "state": paused_snapshot.state.value,
                "frames": [paused_step.start_frame, paused_step.end_frame],
                "silent": bool(abs(paused_step.samples).max() == 0.0),
            },
            "reset": {
                "state": reset_snapshot.state.value,
                "position_frame": reset_snapshot.engine_snapshot.position_frame,
            },
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
