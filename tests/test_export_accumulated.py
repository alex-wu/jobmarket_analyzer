"""Tests for ``jobpipe.duckdb_io.export_accumulated`` — ADR-020 primitive."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from jobpipe.duckdb_io import PublishError, export_accumulated


def _posting_row(
    posting_id: str,
    *,
    ingested_at: datetime,
    title: str = "Data Analyst",
    country: str = "GB",
    first_seen_at: datetime | None = None,
    last_seen_at: datetime | None = None,
) -> dict[str, object]:
    now = pd.Timestamp(ingested_at)
    return {
        "posting_id": posting_id,
        "source": "adzuna",
        "title": title,
        "company": "Acme",
        "location_raw": "Madrid",
        "country": country,
        "region": None,
        "remote": None,
        "salary_min_eur": 50_000.0,
        "salary_max_eur": 60_000.0,
        "salary_period": "annual",
        "salary_annual_eur_p50": 55_000.0,
        "salary_imputed": False,
        "posted_at": now,
        "ingested_at": now,
        "first_seen_at": pd.Timestamp(first_seen_at) if first_seen_at else pd.NaT,
        "last_seen_at": pd.Timestamp(last_seen_at) if last_seen_at else pd.NaT,
        "posting_url": f"https://example.test/jobs/{posting_id}",
        "isco_code": "2511",
        "isco_match_method": "fuzzy",
        "isco_match_score": 0.9,
        "raw_payload": "{}",
        "year_month": pd.Timestamp(ingested_at).strftime("%Y-%m"),
        "adzuna_category": "IT Jobs",
        "contract_type": "permanent",
        "contract_time": "full_time",
        "description": "Synthetic description",
        "location_area": ["UK", "London"],
        "skills": ["SQL", "Python (computer programming)"],
    }


def _write(path: Path, rows: list[dict[str, object]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    # Mirror production: accumulation cols are tz-aware so they survive
    # round-trip as TIMESTAMP WITH TIME ZONE (matches ingested_at).
    for col in ("first_seen_at", "last_seen_at"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], utc=True)
    df.to_parquet(path, index=False)
    return path


def test_dedupes_by_posting_id_across_snapshots(tmp_path: Path) -> None:
    """Two snapshots, same posting in both → one output row."""
    t0 = datetime(2026, 5, 1, tzinfo=UTC)
    t1 = datetime(2026, 5, 8, tzinfo=UTC)
    snap_a = _write(tmp_path / "a.parquet", [_posting_row("p-1", ingested_at=t0)])
    snap_b = _write(tmp_path / "b.parquet", [_posting_row("p-1", ingested_at=t1)])
    out = tmp_path / "latest.parquet"

    count = export_accumulated([snap_a, snap_b], out, preset_id="demo")

    assert count == 1
    df = pd.read_parquet(out)
    assert len(df) == 1
    assert df.loc[0, "posting_id"] == "p-1"


def test_first_seen_is_min_last_seen_is_max(tmp_path: Path) -> None:
    """first_seen_at = MIN(ingested_at); last_seen_at = MAX(ingested_at)."""
    t0 = datetime(2026, 5, 1, tzinfo=UTC)
    t1 = datetime(2026, 5, 8, tzinfo=UTC)
    t2 = datetime(2026, 5, 15, tzinfo=UTC)
    snap_a = _write(tmp_path / "a.parquet", [_posting_row("p-1", ingested_at=t0)])
    snap_b = _write(tmp_path / "b.parquet", [_posting_row("p-1", ingested_at=t1)])
    snap_c = _write(tmp_path / "c.parquet", [_posting_row("p-1", ingested_at=t2)])
    out = tmp_path / "latest.parquet"

    export_accumulated([snap_a, snap_b, snap_c], out, preset_id="demo")

    df = pd.read_parquet(out)
    assert pd.Timestamp(df.loc[0, "first_seen_at"]) == pd.Timestamp(t0)
    assert pd.Timestamp(df.loc[0, "last_seen_at"]) == pd.Timestamp(t2)


def test_preserves_prior_accumulation_first_seen(tmp_path: Path) -> None:
    """When snapshot already carries first_seen_at from prior accumulation,
    MIN preserves it rather than degrading to per-snapshot ingested_at."""
    historical_first = datetime(2026, 1, 1, tzinfo=UTC)
    snap_t1 = datetime(2026, 5, 1, tzinfo=UTC)
    snap_t2 = datetime(2026, 5, 8, tzinfo=UTC)
    # snap_a is itself an accumulation output — first_seen_at populated.
    snap_a = _write(
        tmp_path / "a.parquet",
        [_posting_row("p-1", ingested_at=snap_t1, first_seen_at=historical_first)],
    )
    snap_b = _write(tmp_path / "b.parquet", [_posting_row("p-1", ingested_at=snap_t2)])
    out = tmp_path / "latest.parquet"

    export_accumulated([snap_a, snap_b], out, preset_id="demo")

    df = pd.read_parquet(out)
    assert pd.Timestamp(df.loc[0, "first_seen_at"]) == pd.Timestamp(historical_first)


def test_unique_posting_ids_kept_separately(tmp_path: Path) -> None:
    """Distinct posting_ids round-trip without collapse."""
    t0 = datetime(2026, 5, 1, tzinfo=UTC)
    snap = _write(
        tmp_path / "snap.parquet",
        [
            _posting_row("p-1", ingested_at=t0, country="GB"),
            _posting_row("p-2", ingested_at=t0, country="ES"),
            _posting_row("p-3", ingested_at=t0, country="GB"),
        ],
    )
    out = tmp_path / "latest.parquet"

    export_accumulated([snap], out, preset_id="demo")

    df = pd.read_parquet(out)
    assert len(df) == 3
    assert set(df["posting_id"]) == {"p-1", "p-2", "p-3"}


def test_raises_when_input_empty(tmp_path: Path) -> None:
    with pytest.raises(PublishError, match="no dated parquets"):
        export_accumulated([], tmp_path / "latest.parquet", preset_id="demo")


def test_tolerates_legacy_schema_without_accumulation_cols(tmp_path: Path) -> None:
    """Pre-ADR-020 snapshots predate first_seen_at / last_seen_at. union_by_name
    + COALESCE inside MIN/MAX must fall through to ingested_at gracefully."""
    t0 = datetime(2026, 5, 1, tzinfo=UTC)

    # Build a legacy-schema row: drop the new columns entirely.
    legacy_row = _posting_row("p-1", ingested_at=t0)
    legacy_row.pop("first_seen_at")
    legacy_row.pop("last_seen_at")
    snap_legacy = _write(tmp_path / "legacy.parquet", [legacy_row])

    # Modern snapshot with the new columns.
    snap_modern = _write(
        tmp_path / "modern.parquet",
        [_posting_row("p-1", ingested_at=t0 + timedelta(days=7))],
    )

    out = tmp_path / "latest.parquet"
    export_accumulated([snap_legacy, snap_modern], out, preset_id="demo")

    df = pd.read_parquet(out)
    assert len(df) == 1
    # MIN(COALESCE(first_seen_at, ingested_at)) falls back to ingested_at when
    # the legacy snapshot's first_seen_at is null.
    assert pd.Timestamp(df.loc[0, "first_seen_at"]) == pd.Timestamp(t0)


def test_output_parquet_is_readable_by_duckdb(tmp_path: Path) -> None:
    """Sanity check: the output is a valid parquet, queryable end-to-end."""
    t0 = datetime(2026, 5, 1, tzinfo=UTC)
    snap = _write(tmp_path / "snap.parquet", [_posting_row("p-1", ingested_at=t0)])
    out = tmp_path / "latest.parquet"

    export_accumulated([snap], out, preset_id="demo")

    n = duckdb.sql(f"SELECT count(*) FROM '{out.as_posix()}'").fetchone()
    assert n is not None and n[0] == 1
