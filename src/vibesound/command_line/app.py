"""Complete Phase 6 CLI implemented as a client of the stable local API."""

from __future__ import annotations

import hashlib
import webbrowser
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4, uuid5

import typer

from vibesound import __version__
from vibesound.api.server import _is_loopback_host, run_server
from vibesound.application import (
    ApiIssue,
    ClipLaunchRequest,
    ClipStopRequest,
    ExportJobRequest,
    RenderJobRequest,
    TransactionRequest,
    TransportRequest,
)
from vibesound.command_line.support import (
    CLI_SCHEMA_VERSION,
    DEFAULT_SERVICE_URL,
    CliExit,
    CliFailure,
    CommandResult,
    ProjectContext,
    connected_project,
    emit_stream_failure,
    failed_transaction,
    json_line,
    list_entities,
    read_json,
    read_local_project,
    require_entity_type,
    require_successful_job,
    resolve_selector,
    run_command,
    transaction_request,
    wait_for_job,
)
from vibesound.demo import ensure_demo
from vibesound.project import (
    Project,
    ProjectRepository,
    create_project,
    load_project,
    migrate_project,
    new_project,
    validate_project,
    working_path_for_archive,
)

app = typer.Typer(
    name="vibesound",
    help="A Python-first DAW for musicians and coding agents.",
    no_args_is_help=True,
    add_completion=True,
)
server_app = typer.Typer(help="Inspect the local project service.", no_args_is_help=True)
project_app = typer.Typer(
    help="Create, inspect, validate, and export projects.",
    no_args_is_help=True,
)
entity_app = typer.Typer(help="List and resolve stable project entities.", no_args_is_help=True)
audio_app = typer.Typer(help="Import audio and manage the runtime backend.", no_args_is_help=True)
asset_app = typer.Typer(help="Compatibility aliases for project assets.", no_args_is_help=True)
transport_app = typer.Typer(help="Control project transport.", no_args_is_help=True)
session_app = typer.Typer(help="Launch and stop session slots.", no_args_is_help=True)
transaction_app = typer.Typer(
    help="Preview or atomically commit operation batches.",
    no_args_is_help=True,
)
job_app = typer.Typer(help="Inspect, wait for, and cancel background jobs.", no_args_is_help=True)
events_app = typer.Typer(help="Watch the project event stream.", no_args_is_help=True)

app.add_typer(server_app, name="server")
app.add_typer(project_app, name="project")
app.add_typer(entity_app, name="entity")
app.add_typer(audio_app, name="audio")
app.add_typer(asset_app, name="asset")
app.add_typer(transport_app, name="transport")
app.add_typer(session_app, name="session")
app.add_typer(transaction_app, name="transaction")
app.add_typer(job_app, name="job")
app.add_typer(events_app, name="events")


@app.command()
def version(
    as_json: bool = typer.Option(False, "--json", help="Emit the stable JSON envelope."),
) -> None:
    """Print the installed VibeSound version."""

    run_command(
        "version",
        as_json=as_json,
        action=lambda: CommandResult(
            data={"application_version": __version__, "cli_schema_version": CLI_SCHEMA_VERSION},
            human=(__version__,),
        ),
    )


@app.command()
def doctor(
    as_json: bool = typer.Option(False, "--json", help="Emit the stable JSON envelope."),
) -> None:
    """Report the installed command and contract versions."""

    run_command(
        "doctor",
        as_json=as_json,
        action=lambda: CommandResult(
            data={
                "status": "ready",
                "application_version": __version__,
                "cli_schema_version": CLI_SCHEMA_VERSION,
            },
            human=("VibeSound CLI is installed and ready.",),
        ),
    )


@app.command()
def demo(
    path: Path = typer.Argument(
        Path("vibesound-demo.vibesound-work"),
        help="Generated working-project directory.",
    ),
    host: str = typer.Option("127.0.0.1", help="Loopback address for the local service."),
    port: int = typer.Option(8765, min=1, max=65535),
    serve: bool = typer.Option(True, "--serve/--no-serve"),
    open_browser: bool = typer.Option(
        False,
        "--open",
        help="Open the local browser session after the service binds.",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Validate without creating files."),
    as_json: bool = typer.Option(False, "--json", help="Emit the stable JSON envelope."),
) -> None:
    """Create or open the synthetic demo and optionally start its service."""

    def action() -> CommandResult:
        destination = path.resolve(strict=False)
        if destination.suffix.casefold() != ".vibesound-work":
            raise CliFailure(
                CliExit.USAGE,
                ApiIssue(
                    code="invalid_project_path",
                    path="/path",
                    message="Demo path must end with .vibesound-work",
                ),
            )
        if not _is_loopback_host(host):
            raise CliFailure(
                CliExit.USAGE,
                ApiIssue(code="non_loopback_host", path="/host", message="Host must be loopback"),
            )
        if open_browser and not serve:
            raise CliFailure(
                CliExit.USAGE,
                ApiIssue(
                    code="open_requires_server",
                    path="/open",
                    message="--open requires --serve",
                ),
            )
        if dry_run:
            data = {
                "path": str(destination),
                "host": host,
                "port": port,
                "serve": serve,
                "open_requested": open_browser,
                "browser_opened": False,
            }
            return CommandResult(data=data, human=(f"Would prepare demo at {destination}",))
        project = ensure_demo(destination)
        context = _context(destination, project)
        if serve:
            run_server(
                destination,
                host=host,
                port=port,
                started=lambda actual_host, actual_port: _emit_server_start(
                    actual_host,
                    actual_port,
                    as_json,
                    context,
                    command="demo",
                    open_browser=open_browser,
                ),
            )
        data = {
            "path": str(destination),
            "served": serve,
            "open_requested": open_browser,
        }
        return CommandResult(
            data=data,
            project=context,
            human=(f"Demo ready: {destination} ({project.project_id})",),
        )

    run_command("demo", as_json=as_json, dry_run=dry_run, action=action)


@app.command()
def serve(
    project: Path = typer.Argument(..., help="Project served by this process."),
    host: str = typer.Option("127.0.0.1", help="Loopback bind address."),
    port: int = typer.Option(8765, min=1, max=65535),
    open_browser: bool = typer.Option(
        False,
        "--open",
        help="Open the local browser session after the service binds.",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Validate without binding."),
    as_json: bool = typer.Option(False, "--json", help="Emit machine-readable lifecycle lines."),
) -> None:
    """Run one explicit foreground service for one project."""

    def action() -> CommandResult:
        local = read_local_project(project)
        context = _context(local.path, local.project)
        if not _is_loopback_host(host):
            raise CliFailure(
                CliExit.USAGE,
                ApiIssue(
                    code="non_loopback_host",
                    path="/host",
                    message="VibeSound may bind only to a loopback address",
                ),
                project=context,
            )
        service_url = _service_url(host, port)
        data = {
            "url": service_url,
            "validated": True,
            "open_requested": open_browser,
            "browser_opened": False,
        }
        if dry_run:
            return CommandResult(
                data=data,
                project=context,
                human=(f"Would serve {local.path} on {service_url}",),
            )
        run_server(
            local.path,
            host=host,
            port=port,
            started=lambda actual_host, actual_port: _emit_server_start(
                actual_host,
                actual_port,
                as_json,
                context,
                command="serve",
                open_browser=open_browser,
            ),
        )
        return CommandResult(
            data={**data, "stopped": True},
            project=context,
            human=("VibeSound service stopped.",),
        )

    run_command("serve", as_json=as_json, dry_run=dry_run, action=action)


@server_app.command("status")
def server_status(
    project: Path = typer.Argument(...),
    url: str = typer.Option(DEFAULT_SERVICE_URL, "--url", envvar="VIBESOUND_URL"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Verify service reachability and project ownership."""

    def action() -> CommandResult:
        with connected_project(project, url) as service:
            version_data = service.client.version()
            data = {
                "status": service.readiness.status,
                "service": version_data,
                "url": url,
            }
            return CommandResult(
                data=data,
                project=service.context,
                human=(
                    f"Ready: {service.context.id} at revision {service.context.revision}",
                ),
            )

    run_command("server status", as_json=as_json, action=action)


@server_app.command("capabilities")
def server_capabilities(
    project: Path = typer.Argument(...),
    url: str = typer.Option(DEFAULT_SERVICE_URL, "--url", envvar="VIBESOUND_URL"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Inspect server-advertised behavior."""

    def action() -> CommandResult:
        with connected_project(project, url) as service:
            return CommandResult(
                data=service.client.capabilities(),
                project=service.context,
            )

    run_command("server capabilities", as_json=as_json, action=action)


@server_app.command("schemas")
def server_schemas(
    project: Path = typer.Argument(...),
    url: str = typer.Option(DEFAULT_SERVICE_URL, "--url", envvar="VIBESOUND_URL"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Inspect the stable request schemas exposed by the server."""

    def action() -> CommandResult:
        with connected_project(project, url) as service:
            return CommandResult(data=service.client.schemas(), project=service.context)

    run_command("server schemas", as_json=as_json, action=action)


@project_app.command("init")
def project_init(
    path: Path = typer.Argument(..., help="Destination .vibesound or .vibesound-work project."),
    name: str | None = typer.Option(None, help="Display name; defaults to the path stem."),
    tempo: float = typer.Option(120.0, min=20.0, max=300.0),
    sample_rate: int = typer.Option(44100, min=1, max=192000),
    dry_run: bool = typer.Option(False, "--dry-run", help="Validate without creating files."),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Create an empty portable archive or working project."""

    def action() -> CommandResult:
        destination = path.resolve(strict=False)
        suffix = destination.suffix.casefold()
        if suffix not in {".vibesound", ".vibesound-work"}:
            raise CliFailure(
                CliExit.USAGE,
                ApiIssue(
                    code="invalid_project_path",
                    path="/path",
                    message="Project path must end with .vibesound or .vibesound-work",
                ),
            )
        if destination.exists():
            raise CliFailure(
                CliExit.CONFLICT,
                ApiIssue(
                    code="project_exists",
                    path="/path",
                    message=f"Project already exists: {destination}",
                ),
            )
        candidate = new_project(name or destination.stem, tempo_bpm=tempo, sample_rate=sample_rate)
        if not dry_run:
            if suffix == ".vibesound":
                candidate = create_project(
                    destination,
                    candidate.name,
                    tempo_bpm=tempo,
                    sample_rate=sample_rate,
                )
            else:
                with ProjectRepository.create(
                    destination,
                    candidate.name,
                    tempo_bpm=tempo,
                    sample_rate=sample_rate,
                ) as repository:
                    candidate = repository.get_project()
        context = _context(destination, candidate)
        verb = "Would create" if dry_run else "Created"
        return CommandResult(
            data=candidate.model_dump(mode="json"),
            project=context,
            human=(f"{verb} {destination} ({candidate.project_id})",),
        )

    run_command("project init", as_json=as_json, dry_run=dry_run, action=action)


@project_app.command("show")
def project_show(
    project: Path = typer.Argument(...),
    portable: bool = typer.Option(False, "--portable", help="Read only the immutable archive."),
    url: str = typer.Option(DEFAULT_SERVICE_URL, "--url", envvar="VIBESOUND_URL"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Show the service project, or an archive explicitly with --portable."""

    def action() -> CommandResult:
        if portable:
            loaded, path = _portable_project(project)
            context = _context(path, loaded)
        else:
            with connected_project(project, url) as service:
                loaded = service.client.get_project(service.context.id)
                context = _context(service.local.path, loaded)
        return CommandResult(
            data=loaded.model_dump(mode="json"),
            project=context,
            human=_project_human(loaded),
        )

    run_command("project show", as_json=as_json, action=action)


@project_app.command("validate")
def project_validate(
    project: Path = typer.Argument(...),
    portable: bool = typer.Option(False, "--portable", help="Validate only the archive."),
    url: str = typer.Option(DEFAULT_SERVICE_URL, "--url", envvar="VIBESOUND_URL"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Run service-layered validation, or archive validation with --portable."""

    def action() -> CommandResult:
        if portable:
            loaded, path = _portable_project(project)
            context = _context(path, loaded)
            portable_report = validate_project(path)
            data = portable_report.as_dict()
            issues = [
                ApiIssue(code=item.code, path=item.path, message=item.message)
                for item in portable_report.issues
            ]
        else:
            with connected_project(project, url) as service:
                context = service.context
                service_report = service.client.validate_project(context.id)
                data = service_report.model_dump(mode="json")
                issues = [
                    issue
                    for stage in service_report.stages.values()
                    for issue in stage.issues
                ]
        if issues:
            raise CliFailure(CliExit.VALIDATION, issues, project=context, data=data)
        return CommandResult(
            data=data,
            project=context,
            human=(f"Valid project: {context.path}",),
        )

    run_command("project validate", as_json=as_json, action=action)


@project_app.command("state")
def project_state(
    project: Path = typer.Argument(...),
    url: str = typer.Option(DEFAULT_SERVICE_URL, "--url", envvar="VIBESOUND_URL"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Inspect transport, engine, and audio runtime state."""

    def action() -> CommandResult:
        with connected_project(project, url) as service:
            snapshot = service.client.get_state(service.context.id)
            return CommandResult(
                data=snapshot.model_dump(mode="json"),
                project=service.context,
                human=(
                    f"Transport: {snapshot.engine.mode} at frame {snapshot.engine.position_frame}",
                    f"Audio: {snapshot.audio.state}",
                ),
            )

    run_command("project state", as_json=as_json, action=action)


@project_app.command("migrate")
def project_migrate(
    path: Path = typer.Argument(...),
    dry_run: bool = typer.Option(False, "--dry-run", help="Validate without rewriting."),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Explicitly migrate a portable archive with no attached working sidecar."""

    def action() -> CommandResult:
        resolved = path.resolve(strict=True)
        if resolved.suffix.casefold() != ".vibesound":
            raise CliFailure(
                CliExit.USAGE,
                ApiIssue(
                    code="invalid_project_path",
                    path="/path",
                    message="Only portable .vibesound archives can be migrated",
                ),
            )
        sidecar = working_path_for_archive(resolved)
        if sidecar.exists():
            raise CliFailure(
                CliExit.CONFLICT,
                ApiIssue(
                    code="working_sidecar_attached",
                    path="/path",
                    message=f"Refusing to migrate while a working sidecar exists: {sidecar}",
                ),
            )
        migrated = load_project(resolved) if dry_run else migrate_project(resolved)
        context = _context(resolved, migrated)
        verb = "Would migrate" if dry_run else "Migrated"
        return CommandResult(
            data={"schema_version": migrated.schema_version, "path": str(resolved)},
            project=context,
            human=(f"{verb} {resolved} to schema {migrated.schema_version}",),
        )

    run_command("project migrate", as_json=as_json, dry_run=dry_run, action=action)


@project_app.command("export")
def project_export(
    project: Path = typer.Argument(...),
    output: str = typer.Option(..., "--output", help="Path relative to the export root."),
    wait: bool = typer.Option(True, "--wait/--no-wait"),
    timeout: float = typer.Option(300.0, min=0.1),
    dry_run: bool = typer.Option(False, "--dry-run"),
    url: str = typer.Option(DEFAULT_SERVICE_URL, "--url", envvar="VIBESOUND_URL"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Preview or submit a deterministic portable-export job."""

    def action() -> CommandResult:
        with connected_project(project, url) as service:
            request = ExportJobRequest(output_path=output)
            if dry_run:
                preview = service.client.preview_export(service.context.id, request)
                return CommandResult(
                    data=preview.model_dump(mode="json"),
                    project=service.context,
                    human=(f"Would export revision {preview.revision} to {preview.output_path}",),
                )
            job = service.client.submit_export(service.context.id, request)
            return _job_command_result(service.client, service.context, job, wait, timeout, as_json)

    run_command("project export", as_json=as_json, dry_run=dry_run, action=action)


@project_app.command("detach-source")
def project_detach_source(
    project: Path = typer.Argument(...),
    dry_run: bool = typer.Option(False, "--dry-run"),
    url: str = typer.Option(DEFAULT_SERVICE_URL, "--url", envvar="VIBESOUND_URL"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Detach working state from its immutable source archive."""

    def action() -> CommandResult:
        with connected_project(project, url) as service:
            if not dry_run:
                service.client.resolve_external_change(service.context.id)
            verb = "Would detach" if dry_run else "Detached"
            return CommandResult(
                data={"resolution": "detach_source", "applied": not dry_run},
                project=service.context,
                human=(f"{verb} the portable source from {service.local.path}",),
            )

    run_command("project detach-source", as_json=as_json, dry_run=dry_run, action=action)


@entity_app.command("list")
def entity_list(
    project: Path = typer.Argument(...),
    entity_type: str = typer.Argument(..., metavar="TYPE"),
    url: str = typer.Option(DEFAULT_SERVICE_URL, "--url", envvar="VIBESOUND_URL"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """List tracks, scenes, clips, assets, or slots."""

    def action() -> CommandResult:
        normalized = require_entity_type(entity_type)
        with connected_project(project, url) as service:
            entities = list_entities(service.client, service.context.id, normalized)
            values = [item.model_dump(mode="json") for item in entities]
            return CommandResult(
                data={"entity_type": normalized, "entities": values},
                project=service.context,
                human=tuple(_entity_label(normalized, item) for item in entities)
                or (f"No {normalized} entities.",),
            )

    run_command("entity list", as_json=as_json, action=action)


@entity_app.command("resolve")
def entity_resolve(
    project: Path = typer.Argument(...),
    entity_type: str = typer.Argument(..., metavar="TYPE"),
    name: str = typer.Argument(...),
    url: str = typer.Option(DEFAULT_SERVICE_URL, "--url", envvar="VIBESOUND_URL"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Resolve a unique exact case-insensitive entity name to its UUID."""

    def action() -> CommandResult:
        normalized = require_entity_type(entity_type, named=True)
        with connected_project(project, url) as service:
            entity_id = service.client.resolve_name(service.context.id, normalized, name)
            return CommandResult(
                data={"entity_type": normalized, "name": name, "id": str(entity_id)},
                project=service.context,
                human=(str(entity_id),),
            )

    run_command("entity resolve", as_json=as_json, action=action)


@audio_app.command("import")
@asset_app.command("import")
def audio_import(
    ctx: typer.Context,
    project: Path = typer.Argument(...),
    source: Path = typer.Argument(...),
    idempotency_key: str | None = typer.Option(None, "--idempotency-key"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    url: str = typer.Option(DEFAULT_SERVICE_URL, "--url", envvar="VIBESOUND_URL"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Upload and atomically import one audio asset; clips remain transaction-owned."""

    def action() -> CommandResult:
        try:
            audio_path = source.resolve(strict=True)
        except OSError as error:
            raise CliFailure(
                CliExit.VALIDATION,
                ApiIssue(code="audio_not_found", path="/source", message=str(error)),
            ) from error
        if not audio_path.is_file():
            raise CliFailure(
                CliExit.VALIDATION,
                ApiIssue(code="audio_not_found", path="/source", message=str(audio_path)),
            )
        with connected_project(project, url) as service:
            if idempotency_key is None:
                asset_id = uuid4()
                requested_upload_id = None
            else:
                source_sha256 = _file_sha256(audio_path)
                token = f"vibesound-cli-audio-import:{idempotency_key}:{source_sha256}"
                asset_id = uuid5(service.context.id, f"{token}:asset")
                requested_upload_id = uuid5(service.context.id, f"{token}:upload")
            upload = service.client.upload_audio(
                service.context.id,
                audio_path,
                upload_id=requested_upload_id,
            )
            upload_id = UUID(str(upload["upload_id"]))
            try:
                request = TransactionRequest.model_validate(
                    {
                        "base_revision": service.context.revision,
                        "idempotency_key": idempotency_key,
                        "operations": [
                            {
                                "op": "asset.import",
                                "upload_id": upload_id,
                                "asset_id": asset_id,
                            }
                        ],
                    }
                )
                result = (
                    service.client.preview_transaction(service.context.id, request)
                    if dry_run
                    else service.client.commit_transaction(service.context.id, request)
                )
            finally:
                service.client.discard_upload(service.context.id, upload_id)
            context = _revision_context(
                service.context,
                service.context.revision if dry_run else result.after_revision,
            )
            if not result.ok:
                raise failed_transaction(result, result.errors, context)
            verb = "Would import" if dry_run else "Imported"
            return CommandResult(
                data={
                    "asset_id": str(asset_id),
                    "upload": upload,
                    "transaction": result.model_dump(mode="json"),
                },
                project=context,
                human=(f"{verb} {audio_path.name} as {asset_id}",),
                warnings=result.warnings,
            )

    group = None if ctx.parent is None else ctx.parent.info_name
    command = "asset import" if group == "asset" else "audio import"
    run_command(command, as_json=as_json, dry_run=dry_run, action=action)


@audio_app.command("devices")
def audio_devices(
    project: Path = typer.Argument(...),
    url: str = typer.Option(DEFAULT_SERVICE_URL, "--url", envvar="VIBESOUND_URL"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """List output devices visible to the project service."""

    def action() -> CommandResult:
        with connected_project(project, url) as service:
            devices = service.client.list_devices()
            return CommandResult(
                data={"devices": [item.model_dump(mode="json") for item in devices]},
                project=service.context,
                human=tuple(f"{item.index}: {item.name} ({item.host_api})" for item in devices)
                or ("No output devices available; device-free editing remains available.",),
            )

    run_command("audio devices", as_json=as_json, action=action)


@audio_app.command("restart")
def audio_restart(
    project: Path = typer.Argument(...),
    device: str | None = typer.Option(None, "--device"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    url: str = typer.Option(DEFAULT_SERVICE_URL, "--url", envvar="VIBESOUND_URL"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Validate or restart the audio backend with an optional device."""

    def action() -> CommandResult:
        with connected_project(project, url) as service:
            selected = _device_selector(device)
            devices = service.client.list_devices()
            if selected is not None and not _device_exists(devices, selected):
                raise CliFailure(
                    CliExit.VALIDATION,
                    ApiIssue(
                        code="audio_device_not_found",
                        path="/device",
                        message=f"Output device does not exist: {selected}",
                    ),
                    project=service.context,
                )
            if dry_run:
                data = {"device": selected, "available": True, "restarted": False}
            else:
                snapshot = service.client.restart_audio(selected)
                data = snapshot.model_dump(mode="json")
            verb = "Would restart" if dry_run else "Restarted"
            return CommandResult(
                data=data,
                project=service.context,
                human=(f"{verb} audio backend" + ("" if selected is None else f" on {selected}"),),
            )

    run_command("audio restart", as_json=as_json, dry_run=dry_run, action=action)


def _transport_command(
    operation: str,
    project: Path,
    dry_run: bool,
    url: str,
    as_json: bool,
) -> None:
    def action() -> CommandResult:
        with connected_project(project, url) as service:
            request = TransportRequest(operation=operation)  # type: ignore[arg-type]
            if dry_run:
                snapshot = service.client.get_state(service.context.id)
                data: Any = {
                    "operation": operation,
                    "accepted": False,
                    "current_state": snapshot.model_dump(mode="json"),
                }
            else:
                snapshot = service.client.transport(service.context.id, request)
                data = snapshot.model_dump(mode="json")
            verb = "Would apply" if dry_run else "Applied"
            return CommandResult(
                data=data,
                project=service.context,
                human=(f"{verb} transport {operation}.",),
            )

    run_command(f"transport {operation}", as_json=as_json, dry_run=dry_run, action=action)


@transport_app.command("play")
def transport_play(
    project: Path = typer.Argument(...),
    dry_run: bool = typer.Option(False, "--dry-run"),
    url: str = typer.Option(DEFAULT_SERVICE_URL, "--url", envvar="VIBESOUND_URL"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Start or resume transport."""

    _transport_command("play", project, dry_run, url, as_json)


@transport_app.command("pause")
def transport_pause(
    project: Path = typer.Argument(...),
    dry_run: bool = typer.Option(False, "--dry-run"),
    url: str = typer.Option(DEFAULT_SERVICE_URL, "--url", envvar="VIBESOUND_URL"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Pause transport without resetting position."""

    _transport_command("pause", project, dry_run, url, as_json)


@transport_app.command("stop")
def transport_stop(
    project: Path = typer.Argument(...),
    dry_run: bool = typer.Option(False, "--dry-run"),
    url: str = typer.Option(DEFAULT_SERVICE_URL, "--url", envvar="VIBESOUND_URL"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Stop transport while preserving its position."""

    _transport_command("stop", project, dry_run, url, as_json)


@transport_app.command("reset")
def transport_reset(
    project: Path = typer.Argument(...),
    dry_run: bool = typer.Option(False, "--dry-run"),
    url: str = typer.Option(DEFAULT_SERVICE_URL, "--url", envvar="VIBESOUND_URL"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Stop transport and return to frame zero."""

    _transport_command("reset", project, dry_run, url, as_json)


@session_app.command("launch")
def session_launch(
    project: Path = typer.Argument(...),
    track: str = typer.Option(..., "--track", help="Track UUID or unique name."),
    scene: str = typer.Option(..., "--scene", help="Scene UUID or unique name."),
    dry_run: bool = typer.Option(False, "--dry-run"),
    url: str = typer.Option(DEFAULT_SERVICE_URL, "--url", envvar="VIBESOUND_URL"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Launch the populated slot at a track/scene coordinate."""

    def action() -> CommandResult:
        with connected_project(project, url) as service:
            track_id = resolve_selector(service.client, service.context.id, "track", track)
            scene_id = resolve_selector(service.client, service.context.id, "scene", scene)
            request = ClipLaunchRequest(track_id=track_id, scene_id=scene_id)
            if dry_run:
                slot = next(
                    (
                        item
                        for item in service.client.list_slots(service.context.id)
                        if item.track_id == track_id and item.scene_id == scene_id
                    ),
                    None,
                )
                if slot is None or slot.clip_id is None:
                    raise CliFailure(
                        CliExit.VALIDATION,
                        ApiIssue(
                            code="slot_empty",
                            message="The requested track/scene slot is empty",
                        ),
                        project=service.context,
                    )
                data = {
                    "accepted": False,
                    "track_id": str(track_id),
                    "scene_id": str(scene_id),
                    "clip_id": str(slot.clip_id),
                }
            else:
                result = service.client.launch_slot(service.context.id, request)
                data = result.model_dump(mode="json")
            verb = "Would launch" if dry_run else "Scheduled"
            return CommandResult(
                data=data,
                project=service.context,
                human=(f"{verb} slot {track_id}/{scene_id}",),
            )

    run_command("session launch", as_json=as_json, dry_run=dry_run, action=action)


@session_app.command("stop")
def session_stop(
    project: Path = typer.Argument(...),
    track: str = typer.Option(..., "--track", help="Track UUID or unique name."),
    dry_run: bool = typer.Option(False, "--dry-run"),
    url: str = typer.Option(DEFAULT_SERVICE_URL, "--url", envvar="VIBESOUND_URL"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Stop the active or pending slot on one track."""

    def action() -> CommandResult:
        with connected_project(project, url) as service:
            track_id = resolve_selector(service.client, service.context.id, "track", track)
            request = ClipStopRequest(track_id=track_id)
            if dry_run:
                snapshot = service.client.get_state(service.context.id)
                active = dict(snapshot.engine.active_clip_ids).get(track_id)
                data = {
                    "accepted": False,
                    "track_id": str(track_id),
                    "active_clip_id": None if active is None else str(active),
                }
            else:
                result = service.client.stop_track(service.context.id, request)
                data = result.model_dump(mode="json")
            verb = "Would stop" if dry_run else "Scheduled stop for"
            return CommandResult(
                data=data,
                project=service.context,
                human=(f"{verb} track {track_id}",),
            )

    run_command("session stop", as_json=as_json, dry_run=dry_run, action=action)


def _transaction_command(
    mode: str,
    project: Path,
    operations_file: Path,
    base_revision: int | None,
    idempotency_key: str | None,
    allow_runtime_reset: bool,
    dry_run: bool,
    url: str,
    as_json: bool,
) -> None:
    def action() -> CommandResult:
        document = read_json(operations_file)
        with connected_project(project, url) as service:
            request = transaction_request(
                document,
                current_revision=service.context.revision,
                base_revision=base_revision,
                idempotency_key=idempotency_key,
                allow_runtime_reset=allow_runtime_reset,
            )
            preview = mode == "preview" or dry_run
            result = (
                service.client.preview_transaction(service.context.id, request)
                if preview
                else service.client.commit_transaction(service.context.id, request)
            )
            context = _revision_context(
                service.context,
                service.context.revision if preview else result.after_revision,
            )
            if not result.ok:
                raise failed_transaction(result, result.errors, context)
            verb = "Previewed" if preview else "Committed"
            return CommandResult(
                data=result.model_dump(mode="json"),
                project=context,
                human=(
                    f"{verb} {len(request.operations)} operations at revision "
                    f"{result.after_revision}",
                ),
                warnings=result.warnings,
            )

    run_command(
        f"transaction {mode}",
        as_json=as_json,
        dry_run=dry_run,
        action=action,
    )


@transaction_app.command("preview")
def transaction_preview(
    project: Path = typer.Argument(...),
    operations_file: Path = typer.Argument(..., metavar="OPS_FILE"),
    base_revision: int | None = typer.Option(None, "--base-revision", min=0),
    idempotency_key: str | None = typer.Option(None, "--idempotency-key"),
    allow_runtime_reset: bool = typer.Option(False, "--allow-runtime-reset"),
    url: str = typer.Option(DEFAULT_SERVICE_URL, "--url", envvar="VIBESOUND_URL"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Validate an operation batch without mutating project state."""

    _transaction_command(
        "preview",
        project,
        operations_file,
        base_revision,
        idempotency_key,
        allow_runtime_reset,
        True,
        url,
        as_json,
    )


@transaction_app.command("commit")
def transaction_commit(
    project: Path = typer.Argument(...),
    operations_file: Path = typer.Argument(..., metavar="OPS_FILE"),
    base_revision: int | None = typer.Option(None, "--base-revision", min=0),
    idempotency_key: str | None = typer.Option(None, "--idempotency-key"),
    allow_runtime_reset: bool = typer.Option(False, "--allow-runtime-reset"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    url: str = typer.Option(DEFAULT_SERVICE_URL, "--url", envvar="VIBESOUND_URL"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Atomically commit an operation batch, or preview with --dry-run."""

    _transaction_command(
        "commit",
        project,
        operations_file,
        base_revision,
        idempotency_key,
        allow_runtime_reset,
        dry_run,
        url,
        as_json,
    )


@app.command()
def render(
    project: Path = typer.Argument(...),
    bars: int | None = typer.Option(None, "--bars", min=1),
    seconds: float | None = typer.Option(None, "--seconds", min=0.001),
    commands: Path | None = typer.Option(None, "--commands", help="Ordered render commands JSON."),
    output: str = typer.Option("render.wav", "--output"),
    idempotency_key: str | None = typer.Option(None, "--idempotency-key"),
    wait: bool = typer.Option(True, "--wait/--no-wait"),
    timeout: float = typer.Option(300.0, min=0.1),
    dry_run: bool = typer.Option(False, "--dry-run"),
    url: str = typer.Option(DEFAULT_SERVICE_URL, "--url", envvar="VIBESOUND_URL"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Preview or submit an offline render and wait by default."""

    def action() -> CommandResult:
        render_commands: Any = [] if commands is None else read_json(commands)
        if not isinstance(render_commands, list):
            raise CliFailure(
                CliExit.USAGE,
                ApiIssue(
                    code="invalid_render_commands",
                    path="/commands",
                    message="Render commands file must contain an array",
                ),
            )
        request = RenderJobRequest.model_validate(
            {
                "output_path": output,
                "bars": bars,
                "seconds": seconds,
                "commands": render_commands,
                "idempotency_key": idempotency_key,
            }
        )
        with connected_project(project, url) as service:
            if dry_run:
                preview = service.client.preview_render(service.context.id, request)
                return CommandResult(
                    data=preview.model_dump(mode="json"),
                    project=service.context,
                    human=(f"Would render revision {preview.revision} to {preview.output_path}",),
                )
            job = service.client.submit_render(service.context.id, request)
            return _job_command_result(service.client, service.context, job, wait, timeout, as_json)

    run_command("render", as_json=as_json, dry_run=dry_run, action=action)


@job_app.command("list")
def job_list(
    project: Path = typer.Argument(...),
    url: str = typer.Option(DEFAULT_SERVICE_URL, "--url", envvar="VIBESOUND_URL"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """List retained render and export jobs newest first."""

    def action() -> CommandResult:
        with connected_project(project, url) as service:
            jobs = service.client.list_jobs(service.context.id)
            return CommandResult(
                data={"jobs": [job.model_dump(mode="json") for job in jobs]},
                project=service.context,
                human=tuple(
                    f"{job.job_id} {job.kind} {job.state} {job.progress:.0%}"
                    for job in jobs
                )
                or ("No retained jobs.",),
            )

    run_command("job list", as_json=as_json, action=action)


@job_app.command("show")
def job_show(
    project: Path = typer.Argument(...),
    job_id: UUID = typer.Argument(...),
    url: str = typer.Option(DEFAULT_SERVICE_URL, "--url", envvar="VIBESOUND_URL"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Show one job by UUID."""

    def action() -> CommandResult:
        with connected_project(project, url) as service:
            job = service.client.get_job(service.context.id, job_id)
            return CommandResult(
                data=job.model_dump(mode="json"),
                project=service.context,
                human=(f"{job.job_id}: {job.kind} {job.state} ({job.progress:.0%})",),
            )

    run_command("job show", as_json=as_json, action=action)


@job_app.command("wait")
def job_wait(
    project: Path = typer.Argument(...),
    job_id: UUID = typer.Argument(...),
    timeout: float = typer.Option(300.0, min=0.1),
    url: str = typer.Option(DEFAULT_SERVICE_URL, "--url", envvar="VIBESOUND_URL"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Wait for a job and fail if its terminal state is not completed."""

    def action() -> CommandResult:
        with connected_project(project, url) as service:
            callback = None if as_json else _progress
            job = wait_for_job(
                service.client,
                service.context.id,
                job_id,
                timeout=timeout,
                on_update=callback,
            )
            require_successful_job(job, service.context)
            return CommandResult(
                data=job.model_dump(mode="json"),
                project=service.context,
                human=(f"Completed {job.kind} job {job.job_id}: {job.output_path}",),
            )

    run_command("job wait", as_json=as_json, action=action)


@job_app.command("cancel")
def job_cancel(
    project: Path = typer.Argument(...),
    job_id: UUID = typer.Argument(...),
    dry_run: bool = typer.Option(False, "--dry-run"),
    url: str = typer.Option(DEFAULT_SERVICE_URL, "--url", envvar="VIBESOUND_URL"),
    as_json: bool = typer.Option(False, "--json"),
) -> None:
    """Cancel a queued or running job, or inspect it with --dry-run."""

    def action() -> CommandResult:
        with connected_project(project, url) as service:
            job = (
                service.client.get_job(service.context.id, job_id)
                if dry_run
                else service.client.cancel_job(service.context.id, job_id)
            )
            verb = "Would cancel" if dry_run else "Cancellation requested for"
            return CommandResult(
                data=job.model_dump(mode="json"),
                project=service.context,
                human=(f"{verb} job {job.job_id} (state: {job.state})",),
            )

    run_command("job cancel", as_json=as_json, dry_run=dry_run, action=action)


@events_app.command("watch")
def events_watch(
    project: Path = typer.Argument(...),
    count: int | None = typer.Option(None, "--count", min=1),
    timeout: float | None = typer.Option(None, "--timeout", min=0.1),
    url: str = typer.Option(DEFAULT_SERVICE_URL, "--url", envvar="VIBESOUND_URL"),
    as_json: bool = typer.Option(False, "--json", help="Emit one raw event per JSONL line."),
) -> None:
    """Watch bounded WebSocket events without automatic reconnection."""

    command = "events watch"
    try:
        with connected_project(project, url) as service:
            received = 0
            with service.client.events(service.context.id) as stream:
                while count is None or received < count:
                    event = stream.receive(timeout=timeout)
                    if as_json:
                        typer.echo(json_line(event.model_dump(mode="json")))
                    else:
                        typer.echo(
                            f"{event.type} revision={event.revision} "
                            f"payload={json_line(event.payload)}"
                        )
                    received += 1
    except (Exception, KeyboardInterrupt) as error:
        emit_stream_failure(command, as_json, error)


def _job_command_result(
    client: Any,
    context: ProjectContext,
    job: Any,
    wait: bool,
    timeout: float,
    as_json: bool,
) -> CommandResult:
    if wait:
        job = wait_for_job(
            client,
            context.id,
            job.job_id,
            timeout=timeout,
            on_update=None if as_json else _progress,
        )
        require_successful_job(job, context)
        human = (f"Completed {job.kind} job {job.job_id}: {job.output_path}",)
    else:
        human = (f"Queued {job.kind} job {job.job_id}",)
    return CommandResult(data=job.model_dump(mode="json"), project=context, human=human)


def _progress(job: Any) -> None:
    typer.echo(f"{job.job_id} {job.state} {job.progress:.0%}", err=True)


def _context(path: Path, project: Project) -> ProjectContext:
    return ProjectContext(
        path=str(path.resolve(strict=False)),
        id=project.project_id,
        revision=project.revision.number,
    )


def _revision_context(context: ProjectContext, revision: int) -> ProjectContext:
    return context.model_copy(update={"revision": revision})


def _portable_project(path: Path) -> tuple[Project, Path]:
    resolved = path.resolve(strict=True)
    if resolved.suffix.casefold() != ".vibesound" or not resolved.is_file():
        raise CliFailure(
            CliExit.VALIDATION,
            ApiIssue(
                code="portable_archive_required",
                path="/project",
                message="--portable requires an existing .vibesound archive",
            ),
        )
    return load_project(resolved), resolved


def _project_human(project: Project) -> tuple[str, ...]:
    return (
        f"Project: {project.name}",
        f"ID: {project.project_id}",
        f"Revision: {project.revision.number}",
        f"Schema: {project.schema_version}",
        f"Tracks: {len(project.tracks)}",
        f"Scenes: {len(project.scenes)}",
        f"Clips: {len(project.clips)}",
        f"Assets: {len(project.assets)}",
        f"Slots: {len(project.clip_slots)}",
    )


def _entity_label(entity_type: str, item: Any) -> str:
    del entity_type
    name = getattr(item, "name", None)
    if name is None:
        name = getattr(item, "original_name", None)
    suffix = "" if name is None else f" {name}"
    return f"{item.id}{suffix}"


def _device_selector(value: str | None) -> int | str | None:
    if value is None:
        return None
    stripped = value.strip()
    return int(stripped) if stripped.isdecimal() else stripped


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _device_exists(devices: list[Any], selector: int | str) -> bool:
    if isinstance(selector, int):
        return any(item.index == selector for item in devices)
    matches = [item for item in devices if item.name.casefold() == selector.casefold()]
    return len(matches) == 1


def _service_url(host: str, port: int) -> str:
    rendered_host = f"[{host}]" if ":" in host else host
    return f"http://{rendered_host}:{port}"


def _emit_server_start(
    host: str,
    port: int,
    as_json: bool,
    context: ProjectContext,
    *,
    command: str,
    open_browser: bool = False,
) -> None:
    service_url = _service_url(host, port)
    opened = False
    warning: dict[str, str] | None = None
    if not as_json:
        typer.echo(f"Serving {context.id} on {service_url}")
    if open_browser:
        try:
            opened = bool(webbrowser.open(service_url, new=2))
        except Exception as error:  # pragma: no cover - platform browser boundary
            warning = {
                "code": "browser_open_failed",
                "path": "/open",
                "message": f"Could not open the browser session: {error}",
            }
        if not opened and warning is None:
            warning = {
                "code": "browser_open_failed",
                "path": "/open",
                "message": "The system browser did not accept the open request.",
            }
    if as_json:
        typer.echo(
            json_line(
                {
                    "cli_schema_version": CLI_SCHEMA_VERSION,
                    "ok": True,
                    "command": command,
                    "project": context.model_dump(mode="json"),
                    "dry_run": False,
                    "data": {
                        "status": "starting",
                        "url": service_url,
                        "open_requested": open_browser,
                        "browser_opened": opened,
                    },
                    "warnings": [] if warning is None else [warning],
                    "errors": [],
                }
            )
        )
    elif open_browser:
        if opened:
            typer.echo(f"Opened browser session at {service_url}")
        else:
            assert warning is not None
            typer.echo(f"Warning: {warning['message']} Open {service_url} manually.", err=True)
