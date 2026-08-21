"""VibeSound command-line entry point."""

import json
from pathlib import Path

import typer

from vibesound import __version__
from vibesound.project import (
    AssetImportError,
    ProjectArchiveError,
    create_project,
    import_audio,
    load_project,
    migrate_project,
    validate_project,
)

app = typer.Typer(
    name="vibesound",
    help="A Python-first DAW for musicians and coding agents.",
    no_args_is_help=True,
    add_completion=True,
)
project_app = typer.Typer(help="Create, inspect, validate, and migrate projects.")
asset_app = typer.Typer(help="Manage assets stored inside projects.")
app.add_typer(project_app, name="project")
app.add_typer(asset_app, name="asset")


def _fail(error: Exception) -> None:
    typer.echo(str(error), err=True)
    raise typer.Exit(code=2)


def _json_dump(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


@app.command()
def version() -> None:
    """Print the installed VibeSound version."""

    typer.echo(__version__)


@app.command()
def doctor() -> None:
    """Report the status of the repository bootstrap."""

    typer.echo("VibeSound bootstrap is installed.")


@project_app.command("init")
def project_init(
    path: Path = typer.Argument(..., help="Destination .vibesound project file."),
    name: str | None = typer.Option(None, help="Display name; defaults to the file stem."),
    tempo: float = typer.Option(120.0, min=20.0, max=300.0),
    sample_rate: int = typer.Option(44100, min=1, max=192000),
) -> None:
    """Create a new empty ZIP-backed project."""

    try:
        project = create_project(path, name or path.stem, tempo_bpm=tempo, sample_rate=sample_rate)
    except (ProjectArchiveError, ValueError) as error:
        _fail(error)
    typer.echo(f"Created {path} ({project.project_id})")


@project_app.command("show")
def project_show(
    path: Path = typer.Argument(..., exists=True, readable=True),
    as_json: bool = typer.Option(False, "--json", help="Print the complete project as JSON."),
) -> None:
    """Show project metadata and entity counts."""

    try:
        project = load_project(path)
    except ProjectArchiveError as error:
        _fail(error)
    if as_json:
        typer.echo(_json_dump(project.model_dump(mode="json")))
        return
    typer.echo(f"Project: {project.name}")
    typer.echo(f"ID: {project.project_id}")
    typer.echo(f"Revision: {project.revision.number}")
    typer.echo(f"Schema: {project.schema_version}")
    typer.echo(f"Tracks: {len(project.tracks)}")
    typer.echo(f"Scenes: {len(project.scenes)}")
    typer.echo(f"Clips: {len(project.clips)}")
    typer.echo(f"Assets: {len(project.assets)}")


@project_app.command("validate")
def project_validate(
    path: Path = typer.Argument(..., exists=True, readable=True),
    as_json: bool = typer.Option(False, "--json", help="Print a machine-readable report."),
) -> None:
    """Validate an archive, manifest references, and asset hashes."""

    report = validate_project(path)
    if as_json:
        typer.echo(_json_dump(report.as_dict()))
    elif report.ok:
        typer.echo(f"Valid project: {path}")
    else:
        for issue in report.issues:
            typer.echo(f"{issue.code} {issue.path}: {issue.message}", err=True)
    if not report.ok:
        raise typer.Exit(code=1)


@project_app.command("migrate")
def project_migrate(path: Path = typer.Argument(..., exists=True, readable=True)) -> None:
    """Apply registered schema migrations and explicitly rewrite the archive."""

    try:
        project = migrate_project(path)
    except ProjectArchiveError as error:
        _fail(error)
    typer.echo(f"Migrated {path} to schema {project.schema_version}")


@asset_app.command("import")
def asset_import(
    project: Path = typer.Argument(..., exists=True, readable=True),
    source: Path = typer.Argument(..., exists=True, readable=True),
    as_json: bool = typer.Option(False, "--json", help="Print imported asset metadata as JSON."),
) -> None:
    """Copy an audio file into a project archive."""

    try:
        asset = import_audio(project, source)
    except (AssetImportError, ProjectArchiveError) as error:
        _fail(error)
    if as_json:
        typer.echo(_json_dump(asset.model_dump(mode="json")))
    else:
        typer.echo(f"Imported {asset.original_name} as {asset.id}")
