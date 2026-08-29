"""Small command-line entry point for creating editable Prism project folders."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from prism import PrismError
from prism.sample_library import project_audio_files
from prism.version import __version__


def main(arguments: list[str] | None = None) -> int:
    """Run the Prism project scaffolder."""

    parser = _parser()
    namespace = parser.parse_args(arguments)
    if namespace.command is None:
        parser.print_help()
        return 0
    if namespace.command == "samples":
        try:
            return _print_samples(namespace.project)
        except (OSError, PrismError) as error:
            parser.error(str(error))
    assert namespace.command == "create"
    if namespace.folder is None and not namespace.tutorial:
        parser.error("Give the project a name or use --tutorial.")
    folder = "tutorial" if namespace.folder is None else namespace.folder
    try:
        target = create_project(
            folder,
            name=namespace.name,
            tempo=namespace.tempo,
            tutorial=namespace.tutorial,
        )
    except (OSError, PrismError) as error:
        parser.error(str(error))
    print(f"Created Prism project: {target}")
    script = target / "main.py"
    try:
        run_path = script.relative_to(Path.cwd()).as_posix()
    except ValueError:
        run_path = script.as_posix()
    print(f'Run it with: uv run "{run_path}"')
    if namespace.tutorial:
        print("Tutorial guide: docs/tutorial/README.md")
    return 0


def create_project(
    folder: str | Path,
    *,
    name: str | None = None,
    tempo: float = 120.0,
    tutorial: bool = False,
    _root: str | Path | None = None,
    _timestamp: str | None = None,
) -> Path:
    """Create a timestamped project directory beneath the local projects folder."""

    requested = Path(folder)
    if requested.is_absolute() or len(requested.parts) != 1:
        raise PrismError("Give the project a folder name, not a path.")
    folder_name = requested.name.strip()
    if not folder_name or folder_name in {".", ".."}:
        raise PrismError("The project folder name cannot be empty.")
    timestamp = _timestamp or datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    if re.fullmatch(r"\d{8}-\d{6}", timestamp) is None:
        raise PrismError("The project timestamp is invalid.")
    root = (Path.cwd() if _root is None else Path(_root)).resolve(strict=False)
    target = root / "projects" / f"{folder_name}-{timestamp}"
    if target.exists():
        raise PrismError(f"Timestamped project already exists; try again: {target}")
    if not 20.0 <= tempo <= 300.0:
        raise PrismError("Tempo must be between 20 and 300 BPM.")
    requested_name = "Prism Tutorial" if tutorial and name is None else name
    project_name = _project_name(requested_name, folder_name)
    target.mkdir(parents=True)
    try:
        (target / "sounds").mkdir()
        (target / "renders").mkdir()
        (target / "main.py").write_text(
            _starter_script(project_name, tempo),
            encoding="utf-8",
            newline="\n",
        )
    except OSError:
        _remove_empty_scaffold(target)
        raise
    return target


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="prism",
        description="Create an editable Prism project folder.",
        epilog='example: prism create my-song --name "My Song" --tempo 120',
    )
    subcommands = parser.add_subparsers(dest="command")
    create = subcommands.add_parser(
        "create",
        help="create projects/NAME-TIMESTAMP with main.py, sounds, and renders",
    )
    create.add_argument("folder", nargs="?", help="project folder name, for example my-song")
    create.add_argument("--name", help="song name written into main.py")
    create.add_argument("--tempo", type=float, default=120.0, help="tempo in BPM (default: 120)")
    create.add_argument(
        "--tutorial",
        action="store_true",
        help="create a Prism Tutorial starting project",
    )
    samples = subcommands.add_parser(
        "samples",
        help="list project audio files and duplicate filenames",
    )
    samples.add_argument(
        "project",
        help="project folder or its main.py file",
    )
    return parser


def _print_samples(value: str | Path) -> int:
    requested = Path(value).resolve(strict=False)
    root = requested.parent if requested.name.casefold() == "main.py" else requested
    if not root.is_dir() or not (root / "main.py").is_file():
        raise PrismError("A Prism project must be a folder containing main.py.")
    files = project_audio_files(root)
    if not files:
        print(f"No audio files found in: {root}")
        return 0

    print(f"Audio files in {root}:")
    relative_files = [path.relative_to(root).as_posix() for path in files]
    for path in relative_files:
        print(f"  {path}")

    by_name: dict[str, list[str]] = {}
    for path in relative_files:
        by_name.setdefault(Path(path).name.casefold(), []).append(path)
    duplicates = [paths for paths in by_name.values() if len(paths) > 1]
    if duplicates:
        print("Duplicate filenames need an explicit relative path:")
        for paths in duplicates:
            print(f"  {Path(paths[0]).name}: {', '.join(paths)}")
    else:
        print("Every filename is unique.")
        print("Files under sounds can be used directly; register other folders in main.py.")
    return 0


def _project_name(value: str | None, folder_name: str) -> str:
    if value is not None:
        clean = value.strip()
    else:
        clean = re.sub(r"[-_]+", " ", folder_name).strip().title()
    if not clean:
        raise PrismError("The project name cannot be empty.")
    if len(clean) > 120:
        raise PrismError("The project name cannot exceed 120 characters.")
    return clean


def _starter_script(name: str, tempo: float) -> str:
    return f'''from prism import Project, Uniwave

song = Project(
    {json.dumps(name, ensure_ascii=False)},
    prism_version={json.dumps(__version__)},
    tempo={tempo:g},
)

kick = song.track("Kick", gain_db=-3).drum(
    "kick",
    "x--- x--- x--- x---",
)

bass = song.track("Bass", gain_db=-6).midi(
    "C2 - C2 Eb2 | G1 - Bb1 -",
    instrument=Uniwave.bass(),
    bars=2,
)

song.section("Loop", bars=4, tracks=[kick, bass])

print(song.validate())
print(song.export_midi("renders/song.mid"))
print(song.render("renders/song.wav"))
'''


def _remove_empty_scaffold(target: Path) -> None:
    for child in (target / "sounds", target / "renders"):
        try:
            child.rmdir()
        except OSError:
            pass
    try:
        target.rmdir()
    except OSError:
        pass


if __name__ == "__main__":
    sys.exit(main())
