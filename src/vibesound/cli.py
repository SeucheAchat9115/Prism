"""Initial VibeSound command-line entry point.

The command surface is intentionally small during the repository bootstrap.
Subcommands will be added as the project model and application service land.
"""

import typer

from vibesound import __version__

app = typer.Typer(
    name="vibesound",
    help="A Python-first DAW for musicians and coding agents.",
    no_args_is_help=True,
    add_completion=True,
)


@app.command()
def version() -> None:
    """Print the installed VibeSound version."""

    typer.echo(__version__)


@app.command()
def doctor() -> None:
    """Report the status of the repository bootstrap."""

    typer.echo("VibeSound bootstrap is installed.")
