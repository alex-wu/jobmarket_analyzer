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
    output_filename: str = "postings.parquet",
) -> Path:
    """Write the hive-partitioned bundle + ``manifest.json`` under ``out_root``.

    ``output_filename`` only applies to the flat (``partition_by=[]``) case —
    multi-preset releases pass ``latest-{preset_id}.parquet`` so the asset
    name in the GitHub release is preset-scoped (ADR-019). Hive layout
    ignores it; per-partition files are named by DuckDB.

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
                ) TO '{(postings_dir / output_filename).as_posix()}'
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


# Columns aggregated via ANY_VALUE in export_accumulated. Stable-per-posting
# attributes — duplicates across weekly snapshots agree, so any value works.
_ACCUMULATE_ANY_VALUE_COLS = (
    "source",
    "title",
    "company",
    "location_raw",
    "country",
    "region",
    "remote",
    "salary_min_eur",
    "salary_max_eur",
    "salary_period",
    "salary_annual_eur_p50",
    "salary_imputed",
    "posted_at",
    "posting_url",
    "isco_code",
    "isco_match_method",
    "isco_match_score",
    "raw_payload",
    "year_month",
)


def export_accumulated(
    dated_paths: list[Path],
    out: Path,
    preset_id: str,
) -> int:
    """Recompute the moving ``latest-{preset_id}.parquet`` from dated snapshots.

    ADR-020 pure-function accumulation: given the immutable per-week parquets
    that fall inside the accumulation window, GROUP BY ``posting_id`` and
    derive ``first_seen_at`` / ``last_seen_at`` from MIN/MAX of historical
    ``ingested_at`` (or the prior accumulation's first/last when re-running).

    Returns the row count of the accumulated frame. Raises :class:`PublishError`
    if the input list is empty (caller decides whether that is fatal).
    """
    if not dated_paths:
        raise PublishError(
            f"export_accumulated[{preset_id}]: no dated parquets supplied; "
            "caller should fall back to the fresh fetch."
        )

    paths_sql = ", ".join(f"'{p.as_posix()}'" for p in dated_paths)
    any_value_sql = ",\n            ".join(
        f"ANY_VALUE({col}) AS {col}" for col in _ACCUMULATE_ANY_VALUE_COLS
    )

    out.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(":memory:")
    try:
        # union_by_name=true tolerates schema drift across older snapshots
        # (e.g. pre-ADR-020 archives missing first_seen_at / last_seen_at).
        # COALESCE folds the legacy NaT case into the same MIN/MAX expression.
        # Explicit casts inside COALESCE: per-source frames inject NaT (no tz,
        # writes as TIMESTAMP_NS) while ingested_at is tz-aware (TIMESTAMP WITH
        # TIME ZONE). DuckDB refuses mixed-tz COALESCE without an explicit cast.
        con.sql(
            f"""
            COPY (
                WITH archive AS (
                    SELECT * FROM read_parquet([{paths_sql}], union_by_name=true)
                )
                SELECT
                    posting_id,
                    MIN(COALESCE(
                        CAST(first_seen_at AS TIMESTAMP WITH TIME ZONE),
                        ingested_at
                    )) AS first_seen_at,
                    MAX(COALESCE(
                        CAST(last_seen_at AS TIMESTAMP WITH TIME ZONE),
                        ingested_at
                    )) AS last_seen_at,
                    MAX(ingested_at) AS ingested_at,
                    {any_value_sql}
                FROM archive
                GROUP BY posting_id
            ) TO '{out.as_posix()}' (FORMAT PARQUET);
            """
        )
        row_count_row = con.sql(
            f"SELECT count(*) FROM read_parquet('{out.as_posix()}')"
        ).fetchone()
    finally:
        con.close()

    row_count = int(row_count_row[0]) if row_count_row else 0
    logger.info(
        "publish: accumulated %d unique postings from %d dated parquets → %s",
        row_count,
        len(dated_paths),
        out,
    )
    return row_count
