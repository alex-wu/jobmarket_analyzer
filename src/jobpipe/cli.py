"""``jobpipe`` CLI — Typer entry point.

Three commands wire the phased build:

* ``jobpipe fetch``      — invoke enabled source adapters, write raw Parquet.
* ``jobpipe normalise``  — run :mod:`jobpipe.normalise`, write enriched Parquet.
* ``jobpipe publish``    — partition + export + manifest for GitHub Release upload.

P0 ships skeletons that exit 0 with a stub message. Phases P1+ fill them in.
"""

from __future__ import annotations

from pathlib import Path

import typer

from jobpipe import __version__

app = typer.Typer(
    name="jobpipe",
    help="Job market analytics pipeline. See README.md for the phase plan.",
    no_args_is_help=True,
    add_completion=False,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"jobpipe {__version__}")
        raise typer.Exit


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the version and exit.",
    ),
) -> None:
    """Top-level options."""


@app.command()
def fetch(
    preset: Path = typer.Option(..., "--preset", help="Path to a run preset YAML."),  # noqa: B008
    use_cassettes: bool = typer.Option(
        False,
        "--use-cassettes",
        help="Replay HTTP from tests/cassettes/ instead of making live calls.",
    ),
) -> None:
    """Fan out enabled source adapters; write raw Parquet under data/raw/."""
    typer.echo(f"[P0 skeleton] fetch preset={preset} use_cassettes={use_cassettes}")


@app.command()
def normalise(
    preset: Path = typer.Option(..., "--preset"),  # noqa: B008
) -> None:
    """Normalise + dedupe + ISCO-tag; write enriched Parquet under data/enriched/."""
    typer.echo(f"[P0 skeleton] normalise preset={preset}")


@app.command()
def publish(
    preset: Path = typer.Option(..., "--preset"),  # noqa: B008
) -> None:
    """Export partitioned Parquet + manifest under data/publish/ for GitHub Release upload."""
    typer.echo(f"[P0 skeleton] publish preset={preset}")
