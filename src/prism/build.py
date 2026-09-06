"""Public project discovery and build operations for script-authored Prism songs."""

from __future__ import annotations

import ast
import importlib.metadata
import os
import runpy
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Mapping

from prism.errors import PrismError, ProjectError
from prism.project.builder import Project
from prism.sample_library import project_audio_files
from prism.vst import VSTRegistry

if TYPE_CHECKING:
    from prism.project.builder import ProjectSummary
    from prism.render import ExportProfile, RenderResult


_EXPORT_METHODS = frozenset({"render", "render_stems", "export_midi"})
_NATIVE_DISTRIBUTIONS = ("numpy", "soundfile", "soxr")
_OPTIONAL_DISTRIBUTIONS = ("dawdreamer",)


@dataclass(frozen=True, slots=True)
class BuildInspection:
    """Static facts about a project's source-level build contract."""

    root: Path
    script: Path
    has_build: bool
    top_level_exports: tuple[str, ...]
    top_level_project_constructors: int

    @property
    def migration_required(self) -> bool:
        """Return whether the source needs the explicit build contract."""

        return not self.has_build or bool(self.top_level_exports)

    def as_dict(self) -> dict[str, object]:
        """Return JSON-safe inspection facts without executing the source."""

        return {
            "schema_version": 1,
            "root": str(self.root),
            "script": str(self.script),
            "contract": "build() -> Project",
            "has_build": self.has_build,
            "top_level_exports": list(self.top_level_exports),
            "top_level_project_constructors": self.top_level_project_constructors,
            "migration_required": self.migration_required,
        }


def resolve_project_root(project: str | Path = ".") -> Path:
    """Resolve a project folder or its main.py without executing project code."""

    requested = Path(project).expanduser().resolve(strict=False)
    if requested.name.casefold() == "main.py":
        root = requested.parent
    elif requested.suffix.casefold() == ".py":
        raise PrismError("Pass a project folder or its main.py file.")
    else:
        root = requested
    script = root / "main.py"
    if not root.is_dir() or not script.is_file():
        raise PrismError(
            f"A Prism project must be a folder containing main.py: {root}"
        )
    return root


def build_contract_info(project: str | Path = ".") -> dict[str, object]:
    """Inspect a project source file without importing or running it."""

    root = resolve_project_root(project)
    inspection = _inspect_source(root / "main.py")
    result = inspection.as_dict()
    result["status"] = "ok" if not inspection.migration_required else "warning"
    if inspection.top_level_exports:
        result["message"] = _migration_message()
    elif not inspection.has_build:
        result["message"] = (
            "Define build() -> Project and keep rendering/export calls in the "
            "Python main guard."
        )
    else:
        result["message"] = "The source exposes the explicit build contract."
    return result


def inspect_project(project: str | Path = ".") -> dict[str, object]:
    """Alias for build_contract_info for readable inspection workflows."""

    return build_contract_info(project)


def build_project(
    project: str | Path = ".",
    *,
    validate: bool = False,
    verify_vst: bool = True,
) -> Project:
    """Execute build() and return a Project without running export side effects.

    The source is executed with a non-main module name, so a conventional
    "if __name__ == "__main__"" export block is skipped. Set validate to
    run the project's normal structural and asset validation after building.
    """

    root = resolve_project_root(project)
    inspection = _inspect_source(root / "main.py")
    if inspection.top_level_exports:
        raise ProjectError(
            f"Cannot use the render CLI with {inspection.script.name}: "
            f"{_migration_message()}"
        )
    if not inspection.has_build:
        raise ProjectError(
            f"{inspection.script.name} does not define build() -> Project. "
            f"{_migration_message()}"
        )
    namespace = _execute_source(inspection.script, root)
    builder = namespace.get("build")
    if not callable(builder):
        raise ProjectError(
            f"{inspection.script.name} must define a callable build() -> Project."
        )
    project_result = builder()
    if not isinstance(project_result, Project):
        raise ProjectError(
            f"build() returned {type(project_result).__name__}; it must return Project."
        )
    if project_result.root.resolve(strict=False) != root.resolve(strict=False):
        raise ProjectError(
            "build() returned a Project rooted somewhere else; use the requested "
            "project root for its source and assets."
        )
    if validate:
        project_result.validate(verify_vst=verify_vst)
    return project_result


def build(
    project: str | Path = ".",
    *,
    validate: bool = False,
    verify_vst: bool = True,
) -> Project:
    """Short alias for build_project used by agents and notebook workflows."""

    return build_project(project, validate=validate, verify_vst=verify_vst)


def validate_project(
    project: str | Path = ".",
    *,
    verify_vst: bool = True,
) -> dict[str, object]:
    """Build, validate, and return a JSON-safe validation result."""

    root = resolve_project_root(project)
    built = build_project(root, validate=True, verify_vst=verify_vst)
    summary = built.validate(verify_vst=verify_vst)
    return {
        "schema_version": 1,
        "status": "ok",
        "root": str(root),
        "summary": _summary_dict(summary),
    }


def render_project(
    project: str | Path = ".",
    output: str | Path = "renders/song.wav",
    *,
    bit_depth: Literal[16, 24, 32] = 16,
    channels: Literal["mono", "stereo"] = "stereo",
    sample_rate: int | None = None,
    tail_seconds: float = 0.0,
    profile: ExportProfile | None = None,
    verify_vst: bool = True,
) -> RenderResult:
    """Build, validate, and render a source project as one explicit operation."""

    root = resolve_project_root(project)
    built = build_project(root, validate=True, verify_vst=verify_vst)
    return built.render(
        output,
        bit_depth=bit_depth,
        channels=channels,
        sample_rate=sample_rate,
        tail_seconds=tail_seconds,
        profile=profile,
    )


def doctor_project(
    project: str | Path = ".",
    *,
    build: bool = False,
    verify_vst: bool = True,
) -> dict[str, object]:
    """Report project, dependency, plugin, and asset health.

    Doctor is metadata-only by default. It parses the source and inspects the
    filesystem, but it does not execute main.py until build=True.
    """

    root = resolve_project_root(project)
    try:
        contract = build_contract_info(root)
    except (OSError, PrismError) as error:
        contract = {
            "schema_version": 1,
            "status": "error",
            "root": str(root),
            "script": str(root / "main.py"),
            "message": str(error),
        }
    dependencies = _dependency_diagnostics()
    plugins = _plugin_diagnostics(root)
    assets = _asset_diagnostics(root)
    build_report: dict[str, object] = {
        "status": "not_run",
        "message": (
            "Metadata-only check; pass build=True to execute build() and validate "
            "the project."
        ),
    }
    if build:
        try:
            built = build_project(root, validate=True, verify_vst=verify_vst)
        except Exception as error:
            build_report = {
                "status": "error",
                "message": f"{type(error).__name__}: {error}",
            }
        else:
            build_report = {
                "status": "ok",
                "message": "build() returned a valid Project.",
                "summary": _summary_dict(built.validate(verify_vst=verify_vst)),
            }

    statuses = [
        _status(contract),
        _status(dependencies),
        _status(plugins),
        _status(assets),
    ]
    if build:
        statuses.append(_status(build_report))
    overall = (
        "error"
        if "error" in statuses
        else "warning"
        if "warning" in statuses
        else "ok"
    )
    return {
        "schema_version": 1,
        "status": overall,
        "root": str(root),
        "script": str(root / "main.py"),
        "contract": contract,
        "dependencies": dependencies,
        "plugins": plugins,
        "assets": assets,
        "build": build_report,
        "security": (
            "Build validation executes project Python in the current interpreter; "
            "it is not a security sandbox."
        ),
    }


def _execute_source(script: Path, root: Path) -> dict[str, Any]:
    old_cwd = Path.cwd()
    old_path = list(sys.path)
    try:
        os.chdir(root)
        sys.path.insert(0, str(root))
        return runpy.run_path(str(script), run_name="prism_build")
    except PrismError:
        raise
    except SystemExit as error:
        raise ProjectError(
            f"Executing {script.name} called SystemExit({error.code!r})."
        ) from error
    except Exception as error:
        raise ProjectError(
            f"Executing {script.name} failed with {type(error).__name__}: {error}"
        ) from error
    finally:
        os.chdir(old_cwd)
        sys.path[:] = old_path


def _inspect_source(script: Path) -> BuildInspection:
    try:
        source = script.read_text(encoding="utf-8")
    except OSError as error:
        raise PrismError(f"Cannot read project source: {script}") from error
    try:
        tree = ast.parse(source, filename=str(script))
    except SyntaxError as error:
        location = f" line {error.lineno}" if error.lineno is not None else ""
        raise PrismError(
            f"Cannot parse {script.name}{location}: {error.msg}."
        ) from error

    has_build = any(
        isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef))
        and statement.name == "build"
        for statement in tree.body
    )
    exports: list[str] = []
    constructors = 0
    for statement in tree.body:
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if _is_main_guard(statement):
            continue
        for node in ast.walk(statement):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Attribute) and node.func.attr in _EXPORT_METHODS:
                exports.append(f"{node.func.attr} (line {node.lineno})")
            if isinstance(node.func, ast.Name) and node.func.id == "Project":
                constructors += 1
    return BuildInspection(
        root=script.parent.resolve(strict=False),
        script=script.resolve(strict=False),
        has_build=has_build,
        top_level_exports=tuple(exports),
        top_level_project_constructors=constructors,
    )


def _is_main_guard(statement: ast.stmt) -> bool:
    if not isinstance(statement, ast.If):
        return False
    test = statement.test
    if not isinstance(test, ast.Compare) or len(test.ops) != 1:
        return False
    if not isinstance(test.ops[0], ast.Eq) or len(test.comparators) != 1:
        return False
    left, right = test.left, test.comparators[0]
    return (
        isinstance(left, ast.Name)
        and left.id == "__name__"
        and isinstance(right, ast.Constant)
        and right.value == "__main__"
    ) or (
        isinstance(right, ast.Name)
        and right.id == "__name__"
        and isinstance(left, ast.Constant)
        and left.value == "__main__"
    )


def _migration_message() -> str:
    return (
        "Define def build() -> Project that only constructs and returns the song; "
        "move validate(), render(), render_stems(), and export_midi() calls into "
        "the Python main guard. Existing scripts remain runnable directly."
    )


def _summary_dict(summary: ProjectSummary) -> dict[str, object]:
    return {
        "name": summary.name,
        "tracks": summary.tracks,
        "sections": summary.sections,
        "bars": summary.bars,
        "duration_seconds": summary.duration_seconds,
    }


def _status(value: Mapping[str, object]) -> str:
    status = value.get("status")
    return status if isinstance(status, str) else "ok"


def _installed_distribution(distribution: str) -> dict[str, object]:
    try:
        version = importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return {"status": "missing", "distribution": distribution}
    return {"status": "ok", "distribution": distribution, "version": version}


def _dependency_diagnostics() -> dict[str, object]:
    required = {
        distribution: _installed_distribution(distribution)
        for distribution in _NATIVE_DISTRIBUTIONS
    }
    optional = {
        distribution: _installed_distribution(distribution)
        for distribution in _OPTIONAL_DISTRIBUTIONS
    }
    missing_required = [
        name for name, details in required.items() if _status(details) == "missing"
    ]
    return {
        "status": "error" if missing_required else "ok",
        "required": required,
        "optional": optional,
        "message": (
            "Native offline rendering dependencies are available."
            if not missing_required
            else f"Missing required distributions: {', '.join(missing_required)}."
        ),
    }


def _plugin_diagnostics(root: Path) -> dict[str, object]:
    try:
        entries = VSTRegistry(root).all_entries()
    except (OSError, PrismError) as error:
        return {"status": "error", "message": f"Cannot inspect vst.json: {error}"}
    details: list[dict[str, object]] = []
    missing: list[str] = []
    for entry in entries:
        path = Path(entry.path).expanduser()
        if not path.is_absolute():
            path = root / path
        exists = path.is_file() or path.is_dir()
        if not exists:
            missing.append(entry.alias)
        details.append(
            {
                "alias": entry.alias,
                "platform": entry.platform,
                "path": str(path),
                "exists": exists,
                "sha256": entry.sha256,
            }
        )
    host = _installed_distribution("dawdreamer")
    if not entries:
        return {
            "status": "ok",
            "registered": 0,
            "entries": [],
            "host": host,
            "message": (
                "No VST3 plugins registered; native rendering does not require "
                "the optional VST host."
            ),
        }
    if missing:
        status = "error"
        message = f"Missing registered VST3 paths: {', '.join(missing)}."
    elif _status(host) == "missing":
        status = "error"
        message = (
            "Registered VST3 plugins require the optional dawdreamer extra "
            "before render validation."
        )
    else:
        status = "ok"
        message = "Registered VST3 paths and the optional host are available."
    return {
        "status": status,
        "registered": len(entries),
        "entries": details,
        "host": host,
        "message": message,
    }


def _asset_diagnostics(root: Path) -> dict[str, object]:
    try:
        files = project_audio_files(root)
    except (OSError, PrismError) as error:
        return {"status": "error", "message": f"Cannot inspect project audio: {error}"}
    return {
        "status": "ok",
        "audio_files": len(files),
        "files": [path.relative_to(root).as_posix() for path in files],
        "message": "Project audio folders are readable.",
    }


__all__ = [
    "BuildInspection",
    "build",
    "build_contract_info",
    "build_project",
    "doctor_project",
    "inspect_project",
    "render_project",
    "resolve_project_root",
    "validate_project",
]
