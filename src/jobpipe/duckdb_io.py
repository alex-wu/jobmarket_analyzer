"""Partitioned Parquet export + manifest writer.

P5's publish stage. Reads the enriched bundle written by ``normalise.run()``
and emits a publishable directory layout under ``data/publish/<run_id>/``:

    postings/country=<X>/year_month=<YYYY-MM>/*.parquet
    benchmarks.parquet        # unpartitioned (small, one-shot)
    manifest.json             # provenance + row stats; per ADR-004 the
                              # dashboard reads ``run_id`` to detect staleness

The partition layout is hive-style so DuckDB-WASM in the P6 dashboard reads
it natively without any per-file enumeration. ``COPY ... PARTITION_BY`` is
the DuckDB primitive that produces it. We register the enriched DataFrame
on the connection, derive ``year_month`` in the SQL projection, and let
DuckDB fan the rows out across partitions.
"""

from __future__ import annotations

import json
import logging
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from jobpipe import __version__

logger = logging.getLogger(__name__)

MANIFEST_SCHEMA_VERSION = "1"


class PublishError(RuntimeError):
    """Raised when the publish bundle cannot be materialised."""


def _value_counts(series: pd.Series) -> dict[str, int]:
    """Stable, JSON-safe ``value_counts`` — drops nulls, ints not numpy ints."""
    counts = series.dropna().value_counts()
    return {str(k): int(v) for k, v in counts.items()}


def _postings_stats(df: pd.DataFrame) -> dict[str, Any]:
    return {
        "row_count": len(df),
        "source_counts": _value_counts(df["source"]),
        "country_counts": _value_counts(df["country"]),
        "isco_match_method_counts": _value_counts(df["isco_match_method"]),
    }


def _benchmark_stats(df: pd.DataFrame) -> dict[str, Any]:
    return {
        "row_count": len(df),
        "source_counts": _value_counts(df["source"]),
        "country_counts": _value_counts(df["country"]),
    }


def export_partitioned(
    enriched_postings: Path,
    enriched_benchmarks: Path | None,
    out_root: Path,
    *,
    partition_by: list[str],
    preset_id: str,
    run_id: str,
    git_sha: str | None = None,
) -> Path:
    """Write the hive-partitioned bundle + ``manifest.json`` under ``out_root``.

    Returns ``out_root``. Raises :class:`PublishError` if the postings
    parquet is missing or empty, or if the partition columns aren't all
    present after the SQL projection.
    """
    if not enriched_postings.exists():
        raise PublishError(f"enriched postings not found: {enriched_postings}")

    postings_df = pd.read_parquet(enriched_postings)
    if postings_df.empty:
        raise PublishError(f"enriched postings is empty: {enriched_postings}")

    # `year_month` is derived in SQL; everything else must already exist.
    declared = set(partition_by)
    available = set(postings_df.columns) | {"year_month"}
    missing = declared - available
    if missing:
        raise PublishError(
            f"partition_by references unknown columns: {sorted(missing)}; "
            f"available={sorted(available)}"
        )

    out_root.mkdir(parents=True, exist_ok=True)
    postings_dir = out_root / "postings"
    postings_dir.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(":memory:")
    try:
        con.register("postings_df", postings_df)
        if partition_by:
            # Hive layout: partition columns end up encoded in the directory
            # path and are stripped from the file payload by DuckDB. Re-reading
            # with hive_partitioning=true reconstructs them.
            partition_cols_sql = ", ".join(partition_by)
            con.sql(
                f"""
                COPY (
                    SELECT *, strftime(posted_at, '%Y-%m') AS year_month
                    FROM postings_df
                ) TO '{postings_dir.as_posix()}'
                (FORMAT PARQUET, PARTITION_BY ({partition_cols_sql}), OVERWRITE_OR_IGNORE);
                """
            )
        else:
            # Single flat file — country + year_month stay as data columns
            # so the dashboard can filter on them after a flat-release upload.
            con.sql(
                f"""
                COPY (
                    SELECT *, strftime(posted_at, '%Y-%m') AS year_month
                    FROM postings_df
                ) TO '{(postings_dir / "postings.parquet").as_posix()}'
                (FORMAT PARQUET);
                """
            )
    finally:
        con.close()

    manifest: dict[str, Any] = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "preset_id": preset_id,
        "run_id": run_id,
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "pipeline_version": __version__,
        "git_sha": git_sha,
        "partition_by": list(partition_by),
        "postings": _postings_stats(postings_df),
    }

    if enriched_benchmarks is not None and enriched_benchmarks.exists():
        bench_df = pd.read_parquet(enriched_benchmarks)
        if not bench_df.empty:
            bench_out = out_root / "benchmarks.parquet"
            shutil.copyfile(enriched_benchmarks, bench_out)
            manifest["benchmarks"] = _benchmark_stats(bench_df)
            logger.info("publish: copied %d benchmark rows to %s", len(bench_df), bench_out)

    manifest_path = out_root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    logger.info(
        "publish: %d postings → %s (partitioned by %s)",
        len(postings_df),
        postings_dir,
        partition_by,
    )
    return out_root
