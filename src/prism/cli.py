"""Small command-line entry point for creating editable Prism project folders."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from prism import PrismError


def main(arguments: list[str] | None = None) -> int:
    """Run the Prism project scaffolder."""

    parser = _parser()
    namespace = parser.parse_args(arguments)
    if namespace.command is None:
        parser.print_help()
        return 0
    try:
        target = create_project(
            namespace.folder,
            name=namespace.name,
            tempo=namespace.tempo,
        )
    except (OSError, PrismError) as error:
        parser.error(str(error))
    print(f"Created Prism project: {target}")
    print(f'Run it with: python "{target / "main.py"}"')
    return 0


def create_project(folder: str | Path, *, name: str | None = None, tempo: float = 120.0) -> Path:
    """Create a normal project directory containing a readable starter song."""

    target = Path(folder).expanduser().resolve(strict=False)
    if target.exists():
        raise PrismError(f"Target already exists; choose a new folder: {target}")
    if not 20.0 <= tempo <= 300.0:
        raise PrismError("Tempo must be between 20 and 300 BPM.")
    project_name = _project_name(name, target.name)
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
        help="create a folder with main.py, sounds, and renders",
    )
    create.add_argument("folder", help="new project folder, for example my-song")
    create.add_argument("--name", help="song name written into main.py")
    create.add_argument("--tempo", type=float, default=120.0, help="tempo in BPM (default: 120)")
    return parser


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
    return f'''from prism import Project

song = Project(
    __file__,
    {name!r},
    tempo={tempo:g},
)

kick = song.track("Kick", gain_db=-3).drum(
    "kick",
    "x--- x--- x--- x---",
)

bass = song.track("Bass", gain_db=-6).midi(
    "C2 - C2 Eb2 | G1 - Bb1 -",
    instrument="bass",
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
