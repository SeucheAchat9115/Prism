"""Small command-line entry point for creating editable Prism project folders."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from prism import PrismError, Project
from prism.sample_library import project_audio_files
from prism.version import __version__
from prism.vst import VST3, VSTRegistry
from prism.vst_host import edit_vst3, inspect_vst3


def main(arguments: list[str] | None = None) -> int:
    """Run the Prism project scaffolder."""

    parser = _parser()
    namespace = parser.parse_args(arguments)
    if namespace.command is None:
        parser.print_help()
        return 0
    try:
        if namespace.command == "samples":
            return _print_samples(namespace.project)
        if namespace.command == "plugins":
            return _plugins_command(namespace)
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
        (target / "plugin-states").mkdir()
        VSTRegistry(target).initialize()
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
    plugins = subcommands.add_parser(
        "plugins", help="register, inspect, and edit this project's VST3 plugins"
    )
    plugin_commands = plugins.add_subparsers(dest="plugin_command", required=True)
    add = plugin_commands.add_parser("add", help="add a VST3 path to vst.json")
    add.add_argument("project", help="project folder or main.py")
    add.add_argument("alias", help="short name used in main.py, for example serum")
    add.add_argument("path", help="path to a .vst3 file or bundle")
    add.add_argument("--replace", action="store_true", help="replace this platform's entry")
    listing = plugin_commands.add_parser("list", help="show registered VST3 paths")
    listing.add_argument("project", help="project folder or main.py")
    inspect_command = plugin_commands.add_parser(
        "inspect", help="show parameter names and normalized values"
    )
    inspect_command.add_argument("project", help="project folder or main.py")
    inspect_command.add_argument("alias", help="registered VST alias")
    inspect_command.add_argument("--search", help="show parameter names containing this text")
    inspect_command.add_argument("--parameter", help="show one exact parameter name or #index")
    inspect_command.add_argument("--all", action="store_true", help="show every parameter")
    inspect_command.add_argument(
        "--python", action="store_true", dest="as_python", help="print copyable Python entries"
    )
    inspect_command.add_argument("--state", help="inspect after loading a project state file")
    remove = plugin_commands.add_parser("remove", help="remove an alias from vst.json")
    remove.add_argument("project", help="project folder or main.py")
    remove.add_argument("alias", help="registered VST alias")
    remove.add_argument(
        "--all-platforms", action="store_true", help="remove Windows and Linux entries"
    )
    edit = plugin_commands.add_parser(
        "edit", help="open the state editor without audio preview and save its state"
    )
    edit.add_argument("project", help="project folder or main.py")
    edit.add_argument("alias", help="registered VST alias")
    edit.add_argument("--state", required=True, help="relative project state-file path")
    return parser


def _plugins_command(namespace: argparse.Namespace) -> int:
    root = _project_root(namespace.project)
    registry = VSTRegistry(root)
    if namespace.plugin_command == "add":
        entry = registry.add(namespace.alias, namespace.path, replace=namespace.replace)
        print(f"Registered {entry.alias} for {entry.platform}: {entry.path}")
        print(f"SHA-256: {entry.sha256}")
        return 0
    if namespace.plugin_command == "list":
        entries = registry.all_entries()
        if not entries:
            print(f"No VST3 plugins registered in {registry.path}.")
            return 0
        for entry in entries:
            print(f"{entry.alias} [{entry.platform}] {entry.path}  sha256:{entry.sha256[:12]}")
        return 0
    if namespace.plugin_command == "remove":
        registry.remove(namespace.alias, all_platforms=namespace.all_platforms)
        print(f"Removed {namespace.alias} from {registry.path.name}.")
        return 0
    project = Project("VST3 tools", prism_version=__version__, _script=root / "main.py")
    if namespace.plugin_command == "edit":
        specification = VST3(namespace.alias, state=namespace.state)
        print(
            "Opening the plugin state editor (no audio preview or musical typing).\n"
            "Close the plugin window to save its state."
        )
        result = edit_vst3(project, specification.alias, specification.state or namespace.state)
        baseline = (
            "plugin defaults"
            if result.baseline == "plugin_defaults"
            else "the previously saved state"
        )
        print(f"Compared with {baseline}.")
        if result.parameter_changes:
            print(f"Changed exposed parameters ({len(result.parameter_changes)}):")
            for change in result.parameter_changes:
                unit = f", unit: {change.label}" if change.label else ""
                print(
                    f"  #{change.index}: {change.name}: "
                    f"{change.before:.6g} -> {change.after:.6g} (normalized{unit})"
                )
        elif result.baseline == "plugin_defaults" and result.state_changed:
            print("Captured plugin defaults; no exposed parameter values changed.")
        elif result.state_changed:
            print(
                "Plugin-private state changed; no exposed parameter values changed."
            )
        else:
            print("No changes detected.")
        print(f"Saved plugin state: {result.state_path.relative_to(root).as_posix()}")
        return 0
    assert namespace.plugin_command == "inspect"
    parameters = inspect_vst3(project, namespace.alias, state=namespace.state)
    if namespace.parameter:
        selector = namespace.parameter.casefold()
        parameters = [
            item
            for item in parameters
            if str(item.get("name", "")).casefold() == selector
            or f"#{item.get('index')}" == selector.split(":", 1)[0]
        ]
    elif namespace.search:
        search = namespace.search.casefold()
        parameters = [
            item for item in parameters if search in str(item.get("name", "")).casefold()
        ]
    elif not namespace.all:
        parameters = parameters[:40]
    if not parameters:
        print("No matching parameters.")
        return 0
    for item in parameters:
        selector = f"#{item['index']}: {item['name']}"
        if namespace.as_python:
            print(f"{json.dumps(selector)}: {float(str(item['value'])):.6g},")
        else:
            label = f" {item['label']}" if item.get("label") else ""
            print(f"{selector} = {float(str(item['value'])):.6g}{label}")
    if not namespace.all and not namespace.search and not namespace.parameter:
        print("Showing the first 40 parameters. Add --all or --search TEXT.")
    return 0


def _project_root(value: str | Path) -> Path:
    requested = Path(value).resolve(strict=False)
    root = requested.parent if requested.name.casefold() == "main.py" else requested
    if not root.is_dir() or not (root / "main.py").is_file():
        raise PrismError("A Prism project must be a folder containing main.py.")
    return root


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
    for child in (
        target / "sounds",
        target / "renders",
        target / "plugin-states",
    ):
        try:
            child.rmdir()
        except OSError:
            pass
    try:
        (target / "vst.json").unlink()
    except OSError:
        pass
    try:
        target.rmdir()
    except OSError:
        pass


if __name__ == "__main__":
    sys.exit(main())
