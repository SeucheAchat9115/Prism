"""Exercise one user-installed VST3 through Prism's isolated offline worker."""

from __future__ import annotations

import argparse
import os
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from _support import print_json

from prism.application import (
    ApplicationService,
    PluginAttachRequest,
    PluginParameterRequest,
    PluginStateCaptureRequest,
    RenderJobRequest,
)
from prism.demo import ensure_demo
from prism.plugins import PluginManager


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Trust, scan, attach, control, state-round-trip, restart, and offline-render "
            "one user-installed VST3 effect."
        )
    )
    parser.add_argument(
        "--plugin",
        type=Path,
        required=True,
        help="Path to a user-installed .vst3 file or bundle.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "output",
        help="Base directory for a unique example run.",
    )
    parser.add_argument(
        "--registry-id",
        help="Select one registry UUID when a VST3 container exposes multiple effects.",
    )
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    plugin_path = args.plugin.expanduser().resolve(strict=True)
    if plugin_path.suffix.casefold() != ".vst3":
        raise ValueError("--plugin must point to a .vst3 file or bundle")
    run_dir = args.output_dir.expanduser() / (
        f"vst3-effect-{datetime.now():%Y%m%d-%H%M%S}-{uuid4().hex[:6]}"
    )
    run_dir.mkdir(parents=True, exist_ok=False)
    os.environ["PRISM_PLUGIN_CONFIG"] = str(run_dir / "machine" / "plugins.json")

    manager = PluginManager()
    manager.add_search_path(plugin_path.parent)
    trust = manager.trust(plugin_path)
    registry = manager.scan()
    available = [
        item
        for item in registry.plugins
        if item.available and Path(item.path).resolve(strict=False) == plugin_path
    ]
    if args.registry_id is not None:
        available = [item for item in available if str(item.registry_id) == args.registry_id]
    if not available:
        manager.close()
        errors = [item.error for item in registry.plugins if Path(item.path) == plugin_path]
        raise RuntimeError(f"The selected VST3 did not produce a ready effect: {errors}")
    record = available[0]

    project_path = run_dir / "phase9-demo.prism-work"
    ensure_demo(project_path)
    service = ApplicationService(project_path, plugin_manager=manager)
    try:
        project = service.get_project()
        track = next(item for item in project.tracks if not item.effects)
        attached = service.attach_plugin(
            track.id,
            record.registry_id,
            PluginAttachRequest(base_revision=project.revision.number),
        )
        if not attached.ok:
            raise RuntimeError(attached.errors[0].message)
        effect = next(
            item for item in service.get_project().tracks if item.id == track.id
        ).effects[0]

        parameters = service.plugin_parameters(effect.id)
        parameter_change = None
        if parameters:
            parameter = parameters[0]
            desired = min(1.0, parameter.raw_value + 0.05)
            result = service.update_plugin_parameter(
                effect.id,
                parameter.id,
                PluginParameterRequest(
                    base_revision=service.get_project().revision.number,
                    raw_value=desired,
                ),
            )
            if not result.ok:
                raise RuntimeError(result.errors[0].message)
            parameter_change = {
                "id": parameter.id,
                "before": parameter.raw_value,
                "after": desired,
            }

        captured = service.capture_plugin_state(
            effect.id,
            PluginStateCaptureRequest(base_revision=service.get_project().revision.number),
        )
        if not captured.ok:
            raise RuntimeError(captured.errors[0].message)
        state = next(
            item for item in service.get_project().tracks if item.id == track.id
        ).effects[0].state

        worker_before = service.plugin_worker_status()
        worker_after = service.restart_plugin_worker()
        restored_parameters = service.plugin_parameters(effect.id)

        scene = service.get_project().scenes[0]
        metadata = service.render(
            RenderJobRequest.model_validate(
                {
                    "output_path": "phase9-vst3.wav",
                    "seconds": 2.0,
                    "commands": [
                        {
                            "frame": 0,
                            "operation": "launch_scene",
                            "scene_id": scene.id,
                        }
                    ],
                }
            )
        )
        print_json(
            {
                "run_directory": str(run_dir),
                "project": str(project_path),
                "plugin": {
                    "registry_id": str(record.registry_id),
                    "instance_id": str(effect.id),
                    "name": record.name,
                    "path": record.path,
                    "binary_sha256": trust.binary_sha256,
                },
                "parameter_count": len(parameters),
                "parameter_change": parameter_change,
                "state": None if state is None else state.model_dump(mode="json"),
                "worker_restart": {
                    "before_pid": worker_before.pid,
                    "after_pid": worker_after.pid,
                    "restart_count": worker_after.restart_count,
                    "restored_parameter_count": len(restored_parameters),
                },
                "render": {
                    "path": str(metadata.output_path),
                    "frames": metadata.frames,
                    "sample_rate": metadata.sample_rate,
                },
            }
        )
    finally:
        service.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
