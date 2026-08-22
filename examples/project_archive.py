"""Create, populate, reload, and validate a self-contained VibeSound project."""

from __future__ import annotations

from _support import make_archive_fixture, parse_output_dir, print_json

from vibesound.project import validate_project


def main() -> int:
    run_dir = parse_output_dir(
        "project-archive",
        "Create and validate a ZIP-backed .vibesound project.",
    )
    project_path, project, track, scene, clip = make_archive_fixture(run_dir)
    report = validate_project(project_path)
    print_json(
        {
            "project_path": str(project_path),
            "project_id": project.project_id,
            "revision": project.revision.number,
            "tracks": [track.name],
            "scenes": [scene.name],
            "clips": [clip.name],
            "assets": len(project.assets),
            "valid": report.ok,
        }
    )
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
