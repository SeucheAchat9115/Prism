"""Build and render a complete mini-song with Prism's native synthesizer."""

from __future__ import annotations

import hashlib
from uuid import UUID, uuid5

import numpy as np
import soundfile as sf
from _support import parse_output_dir, print_json

from prism.application import (
    ApplicationService,
    RenderJobRequest,
    SynthAssetRequest,
    TransactionRequest,
)
from prism.audio import FakeAudioBackend
from prism.engine import TransportClock
from prism.project import ProjectRepository
from prism.synthesis import NativeSynthSpec


def _id(project_id: UUID, name: str) -> UUID:
    return uuid5(project_id, f"prism-native-song:{name}")


def main() -> int:
    run_dir = parse_output_dir(
        "native-synth-song",
        "Build drums, bass, pad, and lead tracks with Prism's native synthesizer.",
    )
    working = run_dir / "native-mini-song.prism-work"
    with ProjectRepository.create(
        working,
        "Native Synth Mini-Song",
        tempo_bpm=120.0,
        sample_rate=44_100,
    ):
        pass

    service = ApplicationService(working, backend_factory=FakeAudioBackend)
    try:
        project_id = service.project_id
        specs = {
            "kick": NativeSynthSpec(preset="kick"),
            "snare": NativeSynthSpec(preset="snare", seed=11),
            "hihat": NativeSynthSpec(preset="hihat", seed=17, gain_db=-7.0),
            "bass": NativeSynthSpec(
                preset="bass",
                sequence=["C2", "-", "C2", "Eb2", "G1", "-", "Bb1", "-"],
                bars=2,
                cutoff_hz=780.0,
            ),
            "pad": NativeSynthSpec(
                preset="pad",
                sequence=["C3+Eb3+G3", "-", "Ab2+C3+Eb3", "-"],
                bars=2,
                attack_ms=260.0,
                release_ms=520.0,
                gain_db=-8.0,
            ),
            "lead": NativeSynthSpec(
                preset="lead",
                sequence=["G4", "Bb4", "C5", "-", "G4", "F4", "Eb4", "-"],
                bars=2,
                waveform="triangle",
                gain_db=-8.0,
            ),
        }
        asset_ids: dict[str, UUID] = {}
        for name, spec in specs.items():
            result = service.generate_synth_asset(
                SynthAssetRequest(
                    base_revision=service.get_project().revision.number,
                    filename=f"{name}.wav",
                    spec=spec,
                    asset_id=_id(project_id, f"asset-{name}"),
                    idempotency_key=f"native-song-{name}-v1",
                )
            )
            if not result.ok:
                raise RuntimeError(result.transaction.errors)
            asset_ids[name] = result.asset_id

        track_names = ("Kick", "Snare", "Hi-Hat", "Bass", "Pad", "Lead")
        scene_names = ("Intro", "Verse", "Chorus", "Outro")
        track_ids = {name: _id(project_id, f"track-{name}") for name in track_names}
        scene_ids = {name: _id(project_id, f"scene-{name}") for name in scene_names}
        source_names = {
            "Kick": "kick",
            "Snare": "snare",
            "Hi-Hat": "hihat",
            "Bass": "bass",
            "Pad": "pad",
            "Lead": "lead",
        }
        clip_ids = {name: _id(project_id, f"clip-{name}") for name in track_names}
        assignments = {
            "Intro": ("Hi-Hat", "Pad"),
            "Verse": ("Kick", "Snare", "Hi-Hat", "Bass"),
            "Chorus": track_names,
            "Outro": ("Kick", "Hi-Hat", "Pad"),
        }
        operations: list[dict[str, object]] = []
        for order, name in enumerate(track_names):
            operations.append(
                {
                    "op": "track.create",
                    "track_id": track_ids[name],
                    "name": name,
                    "order": order,
                }
            )
        for order, name in enumerate(scene_names):
            operations.append(
                {"op": "scene.create", "scene_id": scene_ids[name], "name": name, "order": order}
            )
        for name in track_names:
            operations.append(
                {
                    "op": "clip.create",
                    "clip_id": clip_ids[name],
                    "name": f"Native {name}",
                    "asset_id": asset_ids[source_names[name]],
                    "loop": True,
                }
            )
        for scene_name, tracks in assignments.items():
            for track_name in tracks:
                operations.append(
                    {
                        "op": "slot.assign",
                        "track_id": track_ids[track_name],
                        "scene_id": scene_ids[scene_name],
                        "clip_id": clip_ids[track_name],
                    }
                )
        mixer = {
            "Kick": (-3.0, 0.0),
            "Snare": (-7.0, 0.0),
            "Hi-Hat": (-12.0, 0.25),
            "Bass": (-7.0, -0.12),
            "Pad": (-10.0, -0.25),
            "Lead": (-9.0, 0.30),
        }
        for name, (gain_db, pan) in mixer.items():
            operations.append(
                {
                    "op": "mixer.update",
                    "track_id": track_ids[name],
                    "gain_db": gain_db,
                    "pan": pan,
                }
            )
        authored = service.commit_transaction(
            TransactionRequest.model_validate(
                {
                    "base_revision": service.get_project().revision.number,
                    "idempotency_key": "native-song-structure-v1",
                    "operations": operations,
                }
            )
        )
        if not authored.ok:
            raise RuntimeError(authored.errors)

        clock = TransportClock.from_transport(service.get_project().transport)
        two_bars = int(round(clock.frames_per_bar * 2))
        commands: list[dict[str, object]] = []
        for index, scene_name in enumerate(scene_names):
            frame = index * two_bars
            if frame:
                commands.append({"frame": frame, "operation": "stop_all"})
            commands.append(
                {
                    "frame": frame,
                    "operation": "launch_scene",
                    "scene_id": scene_ids[scene_name],
                }
            )
        four_scenes = len(scene_names) * two_bars
        commands.append({"frame": four_scenes, "operation": "stop_all"})
        rendered = service.render(
            RenderJobRequest.model_validate(
                {
                    "output_path": "native-mini-song.wav",
                    "bars": len(scene_names) * 2,
                    "commands": commands,
                }
            )
        )
        samples, sample_rate = sf.read(rendered.output_path, always_2d=True, dtype="float32")
        validation = service.validate()
        if not validation.ok:
            raise RuntimeError(validation.reports)
        print_json(
            {
                "run_directory": str(run_dir),
                "working_project": str(working),
                "revision": service.get_project().revision.number,
                "tracks": list(track_names),
                "scenes": list(scene_names),
                "native_assets": {name: str(asset_id) for name, asset_id in asset_ids.items()},
                "render": {
                    "path": str(rendered.output_path),
                    "frames": int(samples.shape[0]),
                    "sample_rate": sample_rate,
                    "peak": float(np.max(np.abs(samples))),
                    "sha256": hashlib.sha256(rendered.output_path.read_bytes()).hexdigest(),
                    "scheduled_end_frame": four_scenes,
                },
                "validation_ok": validation.ok,
            }
        )
        return 0
    finally:
        service.close()


if __name__ == "__main__":
    raise SystemExit(main())
