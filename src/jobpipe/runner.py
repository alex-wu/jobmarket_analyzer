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
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd
import yaml

# Side-effect imports — each module's @register decorator populates the sources / benchmarks registry.
# Ruff treats the trailing dotted import as redundant with its siblings, hence the targeted noqa.
import jobpipe.benchmarks.cso
import jobpipe.benchmarks.eurostat
import jobpipe.benchmarks.oecd
import jobpipe.sources.adzuna
import jobpipe.sources.ashby
import jobpipe.sources.greenhouse
import jobpipe.sources.lever
import jobpipe.sources.personio  # noqa: F401
from jobpipe import benchmarks, duckdb_io, fx, normalise, sources
from jobpipe.benchmarks._common import last_fetch_mtime, should_skip
from jobpipe.isco import loader as isco_loader
from jobpipe.schemas import BenchmarkSchema, PostingSchema

logger = logging.getLogger(__name__)


class EmptyRunError(RuntimeError):
    """Raised when every enabled source returned zero rows."""


class PresetError(ValueError):
    """Raised when the preset YAML is malformed or references unknown adapters."""


class NoRawRunError(FileNotFoundError):
    """Raised when ``run_normalise`` cannot find any raw bundle for the preset."""


class NoEnrichedRunError(FileNotFoundError):
    """Raised when ``run_publish`` cannot find any enriched bundle for the preset."""


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

    # Coerce dtypes per-frame so concat doesn't have to infer across mixed
    # all-NA / real-valued columns (silences pandas 2.x FutureWarning).
    # PostingSchema has coerce=True; this is the canonical dtype map.
    frames = [PostingSchema.validate(f, lazy=True) for f in frames]
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


def fetch_benchmarks(
    preset: dict[str, Any],
    out_root: Path,
    *,
    now: datetime | None = None,
) -> list[Path]:
    """Fan out to enabled benchmark adapters; return parquet paths written.

    Fail-isolated per adapter (one's HTTP error logs and is swallowed).
    Per-adapter ``min_interval_hours`` throttles re-fetch — if the most
    recent parquet under ``data/raw/benchmarks/<name>/`` is younger than
    the configured window, we skip and let the previous fetch stand.
    A zero-benchmark run is not a fatal error; postings remain the
    primary signal (CLAUDE.md hard rule).
    """
    declared = preset.get("benchmarks", {}) or {}
    if not isinstance(declared, dict) or not declared:
        return []

    written: list[Path] = []
    current = now or datetime.now(UTC)
    rates_cache: dict[str, float] | None = None

    for name, raw_cfg in declared.items():
        if not raw_cfg.get("enabled", False):
            logger.info("benchmark %s: disabled, skipping", name)
            continue
        try:
            adapter = benchmarks.get(name)
        except KeyError:
            logger.warning("benchmark %s: not registered, skipping", name)
            continue

        cfg = adapter.config_model(**{k: v for k, v in raw_cfg.items() if k != "enabled"})

        adapter_dir = out_root / "raw" / "benchmarks" / name
        last_fetch = last_fetch_mtime(adapter_dir)
        throttle_hours = int(getattr(cfg, "min_interval_hours", 0))
        if should_skip(current, last_fetch, throttle_hours):
            logger.info(
                "benchmark %s: throttle skip (last_fetch=%s, window=%dh)",
                name,
                last_fetch,
                throttle_hours,
            )
            continue

        try:
            if rates_cache is None:
                rates_cache = fx.load_rates()
            try:
                df = adapter.fetch(cfg, rates=rates_cache)
            except TypeError:
                # Test-fixture adapters may not accept the rates kwarg.
                df = adapter.fetch(cfg)
        except Exception:
            logger.exception(
                "benchmark %s: fetch failed; continuing with other benchmarks",
                name,
            )
            continue

        if df.empty:
            logger.warning("benchmark %s: returned zero rows", name)
            continue

        try:
            BenchmarkSchema.validate(df, lazy=True)
        except Exception:
            logger.exception("benchmark %s: schema validation failed; skipping write", name)
            continue

        adapter_dir.mkdir(parents=True, exist_ok=True)
        run_id = current.strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
        out_path = adapter_dir / f"{run_id}.parquet"
        df.to_parquet(out_path, index=False)
        logger.info("benchmark %s: %d rows → %s", name, len(df), out_path)
        written.append(out_path)

    return written


def _load_latest_benchmarks(out_root: Path) -> pd.DataFrame:
    """Concat each enabled benchmark adapter's most-recent parquet."""
    root = out_root / "raw" / "benchmarks"
    if not root.exists():
        return pd.DataFrame()
    frames: list[pd.DataFrame] = []
    for adapter_dir in sorted(root.iterdir()):
        if not adapter_dir.is_dir():
            continue
        parquets = sorted(
            adapter_dir.glob("*.parquet"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not parquets:
            continue
        frames.append(pd.read_parquet(parquets[0]))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def run_fetch(preset_path: Path, out_root: Path = Path("data")) -> Path:
    """Top-level entry point for the ``jobpipe fetch`` CLI command."""
    preset = load_preset(preset_path)
    df = fetch_sources(preset)
    out = write_raw_parquet(df, preset["preset_id"], out_root)
    fetch_benchmarks(preset, out_root)
    return out


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
    labels = isco_loader.load_isco_labels()
    since_days = preset.get("normalise", {}).get("since_days")
    enriched = normalise.run(raw_df, rates, labels_df=labels, since_days=since_days)
    logger.info(
        "normalise: %d rows after dedupe (%d collapsed)",
        len(enriched),
        len(raw_df) - len(enriched),
    )

    out_dir = out_root / "enriched" / raw_path.parent.name
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "postings.parquet"
    enriched.to_parquet(out, index=False)

    bench_df = _load_latest_benchmarks(out_root)
    if not bench_df.empty:
        try:
            BenchmarkSchema.validate(bench_df, lazy=True)
        except Exception:
            logger.exception("normalise: benchmark concat failed schema validation; skipping write")
        else:
            bench_out = out_dir / "benchmarks.parquet"
            bench_df.to_parquet(bench_out, index=False)
            logger.info("normalise: %d benchmark rows → %s", len(bench_df), bench_out)

    return out


def find_latest_enriched(preset_id: str, out_root: Path) -> tuple[Path, Path | None]:
    """Return ``(postings_parquet, benchmarks_parquet_or_none)`` for the newest enriched run.

    Raises :class:`NoEnrichedRunError` if no enriched bundle exists.
    """
    enriched_root = out_root / "enriched"
    candidates = sorted(
        (p for p in enriched_root.glob(f"{preset_id}__*") if p.is_dir()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for d in candidates:
        postings = d / "postings.parquet"
        if postings.exists():
            bench = d / "benchmarks.parquet"
            return postings, (bench if bench.exists() else None)
    raise NoEnrichedRunError(
        f"no enriched bundle for preset {preset_id!r} under {enriched_root}; "
        "run `jobpipe normalise` first"
    )


def _resolve_git_sha() -> str | None:
    """Best-effort git SHA: ``GITHUB_SHA`` in CI, else ``git rev-parse HEAD``."""
    env_sha = os.environ.get("GITHUB_SHA")
    if env_sha:
        return env_sha
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    sha = result.stdout.strip()
    return sha or None


def run_publish(preset_path: Path, out_root: Path = Path("data")) -> Path:
    """Top-level entry point for the ``jobpipe publish`` CLI command.

    Resolves the newest enriched bundle for the preset, reads ``publish:``
    from the preset YAML, and emits a hive-partitioned + manifest bundle
    under ``<out_root>/publish/<same run_id>/``. The ``run_id`` propagates
    through all three stages (raw → enriched → publish) so traceability is
    trivial.
    """
    preset = load_preset(preset_path)
    publish_cfg = preset.get("publish")
    if not isinstance(publish_cfg, dict):
        raise PresetError(f"preset {preset_path} is missing required mapping 'publish'")
    partition_by_raw = publish_cfg.get("partition_by")
    if not isinstance(partition_by_raw, list):
        raise PresetError(f"preset {preset_path}: 'publish.partition_by' must be a list")
    # Empty list is valid — produces a single flat postings.parquet (see duckdb_io).
    partition_by = [str(c) for c in partition_by_raw]

    preset_id = str(preset["preset_id"])
    postings_path, bench_path = find_latest_enriched(preset_id, out_root)
    run_id = postings_path.parent.name  # `<preset_id>__<timestamp>-<hex>`

    bundle_root = out_root / "publish" / run_id
    git_sha = _resolve_git_sha()
    duckdb_io.export_partitioned(
        postings_path,
        bench_path,
        bundle_root,
        partition_by=partition_by,
        preset_id=preset_id,
        run_id=run_id,
        git_sha=git_sha,
    )
    return bundle_root
