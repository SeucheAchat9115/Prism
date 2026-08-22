"""Launch, render, and stop a clip using the deterministic session engine."""

from __future__ import annotations

from _support import action_summary, event_summary, make_memory_fixture, print_json

from vibesound.engine import SessionEngine


def main() -> int:
    project, provider, track, scene, _ = make_memory_fixture(
        sample_rate=8000,
        quantization="beat",
        loop=True,
    )
    engine = SessionEngine(project, provider)
    launch = engine.launch_slot(track.id, scene.id)
    engine.play()
    playing_step = engine.advance(1024)
    stop = engine.stop_all()
    stopped_step = engine.advance(4096)
    snapshot = engine.snapshot()

    print_json(
        {
            "launch": action_summary(launch),
            "playing_step": {
                "frames": [playing_step.start_frame, playing_step.end_frame],
                "peak": float(abs(playing_step.samples).max()),
                "events": event_summary(playing_step.events),
            },
            "stop": action_summary(stop),
            "stopped_step": {
                "frames": [stopped_step.start_frame, stopped_step.end_frame],
                "events": event_summary(stopped_step.events),
            },
            "final_state": {
                "mode": snapshot.mode.value,
                "position_frame": snapshot.position_frame,
                "active_clips": len(snapshot.active_clip_ids),
            },
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
