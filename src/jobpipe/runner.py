"""Runner: load a preset YAML and orchestrate enabled source adapters.

Fan-out is fail-isolated per adapter: one source's failure does not abort the
run; the runner concatenates whatever succeeded. A run with zero rows across
all enabled sources is a loud failure (raised as :class:`EmptyRunError`).

P1 covers source fan-out + raw Parquet write. P2 adds the normalise
orchestrator that consumes the latest raw bundle and writes the strict-schema
enriched Parquet. Benchmarks and publish land in P4 / P5.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd
import yaml

import jobpipe.sources.adzuna  # noqa: F401  -- register("adzuna") side-effect
from jobpipe import fx, normalise, sources
from jobpipe.schemas import PostingSchema

logger = logging.getLogger(__name__)


class EmptyRunError(RuntimeError):
    """Raised when every enabled source returned zero rows."""


class PresetError(ValueError):
    """Raised when the preset YAML is malformed or references unknown adapters."""


class NoRawRunError(FileNotFoundError):
    """Raised when ``run_normalise`` cannot find any raw bundle for the preset."""


def load_preset(path: Path) -> dict[str, Any]:
    """Parse and lightly validate a preset YAML."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PresetError(f"preset not found: {path}") from exc
    except yaml.YAMLError as exc:
        raise PresetError(f"preset {path} is not valid YAML: {exc}") from exc

    if not isinstance(raw, dict):
        raise PresetError(f"preset {path} must be a YAML mapping at the top level")
    if "preset_id" not in raw:
        raise PresetError(f"preset {path} is missing required field 'preset_id'")
    if "sources" not in raw or not isinstance(raw["sources"], dict):
        raise PresetError(f"preset {path} is missing required mapping 'sources'")

    return raw


def fetch_sources(preset: dict[str, Any]) -> pd.DataFrame:
    """Fan out to enabled source adapters; return the concatenated DataFrame.

    Each adapter's config is validated against its ``config_model``. HTTP
    failures inside one adapter are logged and swallowed so the run continues.
    """
    frames: list[pd.DataFrame] = []
    declared = preset["sources"]

    for name, raw_cfg in declared.items():
        if not raw_cfg.get("enabled", False):
            logger.info("source %s: disabled, skipping", name)
            continue
        try:
            adapter = sources.get(name)
        except KeyError:
            logger.warning("source %s: not registered, skipping", name)
            continue

        cfg = adapter.config_model(**{k: v for k, v in raw_cfg.items() if k != "enabled"})
        try:
            df = adapter.fetch(cfg)
        except Exception:
            logger.exception("source %s: fetch failed; continuing with other sources", name)
            continue

        if df.empty:
            logger.warning("source %s: returned zero rows", name)
            continue

        logger.info("source %s: %d rows", name, len(df))
        frames.append(df)

    if not frames:
        raise EmptyRunError(
            "no postings returned from any enabled source — check credentials and connectivity"
        )

    combined = pd.concat(frames, ignore_index=True)
    PostingSchema.validate(combined, lazy=True)
    return combined


def write_raw_parquet(df: pd.DataFrame, preset_id: str, out_root: Path) -> Path:
    """Write the concatenated raw frame to ``data/raw/<run_id>/postings_raw.parquet``."""
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    run_dir = out_root / "raw" / f"{preset_id}__{run_id}"
    run_dir.mkdir(parents=True, exist_ok=True)
    out = run_dir / "postings_raw.parquet"
    df.to_parquet(out, index=False)
    return out


def run_fetch(preset_path: Path, out_root: Path = Path("data")) -> Path:
    """Top-level entry point for the ``jobpipe fetch`` CLI command."""
    preset = load_preset(preset_path)
    df = fetch_sources(preset)
    return write_raw_parquet(df, preset["preset_id"], out_root)


def find_latest_raw(preset_id: str, out_root: Path) -> Path:
    """Return the most-recent ``data/raw/<preset_id>__*/postings_raw.parquet``.

    Raises :class:`NoRawRunError` when no run directory matches.
    """
    raw_root = out_root / "raw"
    candidates = sorted(
        (p for p in raw_root.glob(f"{preset_id}__*") if p.is_dir()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for d in candidates:
        parquet = d / "postings_raw.parquet"
        if parquet.exists():
            return parquet
    raise NoRawRunError(
        f"no raw bundle for preset {preset_id!r} under {raw_root}; run `jobpipe fetch` first"
    )


def run_normalise(preset_path: Path, out_root: Path = Path("data")) -> Path:
    """Top-level entry point for the ``jobpipe normalise`` CLI command.

    Resolves the latest raw bundle for the preset, fetches ECB rates, calls
    :func:`jobpipe.normalise.run`, and writes the enriched Parquet under
    ``data/enriched/<same run_id>/postings.parquet`` — same run_id as the
    raw input, so the two are trivially traceable.
    """
    preset = load_preset(preset_path)
    raw_path = find_latest_raw(preset["preset_id"], out_root)
    raw_df = pd.read_parquet(raw_path)
    logger.info("normalise: %d raw rows from %s", len(raw_df), raw_path)

    rates = fx.load_rates()
    enriched = normalise.run(raw_df, rates)
    logger.info(
        "normalise: %d rows after dedupe (%d collapsed)",
        len(enriched),
        len(raw_df) - len(enriched),
    )

    out_dir = out_root / "enriched" / raw_path.parent.name
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "postings.parquet"
    enriched.to_parquet(out, index=False)
    return out
