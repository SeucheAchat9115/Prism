"""Perform a small scene-set performance with the deterministic engine."""

from __future__ import annotations

from _support import action_summary, event_summary, make_music_fixture, parse_output_dir, print_json

from vibesound.engine import SessionEngine, TransportClock
from vibesound.rendering import prepare_archive_playback_project


def main() -> int:
    run_dir = parse_output_dir(
        "session-performance",
        "Launch quantized scenes and stop them with the deterministic engine.",
    )
    project_path, project, tracks, scenes, _ = make_music_fixture(run_dir)
    prepared = prepare_archive_playback_project(project_path, project)
    clock = TransportClock.from_transport(prepared.project.transport)
    bar = int(clock.frames_per_bar)
    engine = SessionEngine(prepared.project, prepared.sources)
    launch = engine.launch_scene(scenes["Groove"].id)
    engine.play()
    playing_step = engine.advance(bar // 2)
    switch = engine.launch_scene(scenes["Breakdown"].id)
    switched_step = engine.advance(bar)
    stop = engine.stop_all()
    stopped_step = engine.advance(bar)
    snapshot = engine.snapshot()

    print_json(
        {
            "project_path": str(project_path),
            "tracks": list(tracks),
            "scenes": list(scenes),
            "launch": action_summary(launch),
            "playing_step": {
                "frames": [playing_step.start_frame, playing_step.end_frame],
                "peak": float(abs(playing_step.samples).max()),
                "events": event_summary(playing_step.events),
            },
            "scene_switch": action_summary(switch),
            "switched_step": {
                "frames": [switched_step.start_frame, switched_step.end_frame],
                "peak": float(abs(switched_step.samples).max()),
                "events": event_summary(switched_step.events),
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
