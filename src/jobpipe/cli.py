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
import re
from pathlib import Path

import typer

from jobpipe import __version__
from jobpipe.duckdb_io import PublishError
from jobpipe.gate import GateError, run_gate
from jobpipe.runner import (
    EmptyRunError,
    NoEnrichedRunError,
    NoRawRunError,
    PresetError,
    run_fetch,
    run_normalise,
    run_publish,
)

# Query-param names treated as secret. Matched case-insensitively; both
# underscore and hyphen forms covered. See DECISIONS.md ADR-015.
_CREDENTIAL_PARAMS = ("app_id", "app_key", "api_key", "api-key")
_CREDENTIAL_RE = re.compile(
    r"(?i)\b(" + "|".join(re.escape(p) for p in _CREDENTIAL_PARAMS) + r")=[^&\s'\"]+"
)


class CredentialScrubFilter(logging.Filter):
    """Replace credential query-param values in log records with ``REDACTED``.

    httpx + httpcore log full request URLs at INFO. Adzuna (and likely future
    free-tier sources) pass credentials as URL query params, so anything
    captured to the GitHub Actions workflow log would otherwise expose them.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str) and "=" in record.msg:
            record.msg = _CREDENTIAL_RE.sub(r"\1=REDACTED", record.msg)
        if record.args:
            record.args = tuple(
                _CREDENTIAL_RE.sub(r"\1=REDACTED", a) if isinstance(a, str) else a
                for a in record.args
            )
        return True


def _install_credential_scrub() -> None:
    """Attach the scrubber to httpx + httpcore loggers (idempotent)."""
    scrub = CredentialScrubFilter()
    for name in ("httpx", "httpcore"):
        lg = logging.getLogger(name)
        if not any(isinstance(f, CredentialScrubFilter) for f in lg.filters):
            lg.addFilter(scrub)


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
    _install_credential_scrub()
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
    preset: Path = typer.Option(..., "--preset", help="Path to a run preset YAML."),  # noqa: B008
    out_root: Path = typer.Option(  # noqa: B008
        Path("data"),
        "--out-root",
        help="Where data/raw and data/enriched live. Defaults to ./data.",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable INFO logging."),
) -> None:
    """Normalise + dedupe; write enriched Parquet under <out_root>/enriched/."""
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    _install_credential_scrub()
    try:
        out = run_normalise(preset, out_root=out_root)
    except PresetError as exc:
        typer.secho(f"preset error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2) from exc
    except NoRawRunError as exc:
        typer.secho(f"normalise failed: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2) from exc

    typer.echo(str(out))


@app.command()
def publish(
    preset: Path = typer.Option(..., "--preset", help="Path to a run preset YAML."),  # noqa: B008
    out_root: Path = typer.Option(  # noqa: B008
        Path("data"),
        "--out-root",
        help="Where data/enriched and data/publish live. Defaults to ./data.",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable INFO logging."),
) -> None:
    """Export partitioned Parquet + manifest under data/publish/ for GitHub Release upload."""
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    _install_credential_scrub()
    try:
        out = run_publish(preset, out_root=out_root)
    except PresetError as exc:
        typer.secho(f"preset error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2) from exc
    except NoEnrichedRunError as exc:
        typer.secho(f"publish failed: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2) from exc
    except PublishError as exc:
        typer.secho(f"publish failed: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2) from exc

    typer.echo(str(out))


@app.command()
def gate(
    manifest: Path = typer.Option(..., "--manifest", help="Path to manifest.json."),  # noqa: B008
    preset: Path = typer.Option(..., "--preset", help="Path to the same preset YAML."),  # noqa: B008
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable INFO logging."),
) -> None:
    """Assert the published manifest meets per-preset row + coverage thresholds."""
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    _install_credential_scrub()
    try:
        run_gate(manifest, preset)
    except PresetError as exc:
        typer.secho(f"preset error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2) from exc
    except GateError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=2) from exc

    typer.echo("gate ok")
