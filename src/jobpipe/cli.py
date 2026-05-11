"""``jobpipe`` CLI — Typer entry point.

Three commands wire the phased build:

* ``jobpipe fetch``      — invoke enabled source adapters, write raw Parquet.
* ``jobpipe normalise``  — run :mod:`jobpipe.normalise`, write enriched Parquet.
* ``jobpipe publish``    — partition + export + manifest for GitHub Release upload.

P1 wires ``fetch`` to :mod:`jobpipe.runner`. ``normalise`` and ``publish`` are
still skeletons until P2 / P5.
"""

from __future__ import annotations

import logging
from pathlib import Path

import typer

from jobpipe import __version__
from jobpipe.runner import EmptyRunError, PresetError, run_fetch

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
    out_root: Path = typer.Option(  # noqa: B008
        Path("data"),
        "--out-root",
        help="Where data/raw/... lands. Defaults to ./data.",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable INFO logging."),
) -> None:
    """Fan out enabled source adapters; write raw Parquet under <out_root>/raw/."""
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        out = run_fetch(preset, out_root=out_root)
    except PresetError as exc:
        typer.secho(f"preset error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2) from exc
    except EmptyRunError as exc:
        typer.secho(f"run failed: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2) from exc

    typer.echo(str(out))


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
