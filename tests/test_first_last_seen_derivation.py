"""Schema contract for ADR-020 accumulation columns.

`first_seen_at` and `last_seen_at` are nullable and populated only by
`duckdb_io.export_accumulated()`. Per-source / per-run frames leave them NaT;
the strict-mode `PostingSchema` must accept both shapes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pandas as pd

from jobpipe.schemas import PostingSchema


def _row(idx: int, **overrides: Any) -> dict[str, Any]:
    now = pd.Timestamp(datetime.now(UTC))
    base: dict[str, Any] = {
        "posting_id": f"posting-{idx:04d}",
        "source": "fake",
        "title": f"Data Analyst {idx}",
        "company": "Acme",
        "country": "ES",
        "work_arrangement": None,
        "salary_min_eur": 50_000.0,
        "salary_max_eur": 60_000.0,
        "salary_period": "annual",
        "salary_annual_eur_p50": 55_000.0,
        "salary_imputed": False,
        "posted_at": now,
        "ingested_at": now,
        "first_seen_at": pd.NaT,
        "last_seen_at": pd.NaT,
        "posting_url": f"https://example.test/jobs/{idx}",
        "isco_code": None,
        "isco_match_method": None,
        "isco_match_score": None,
        "raw_payload": "{}",
        "adzuna_category": None,
        "contract_type": None,
        "contract_time": None,
        "description": None,
        "location_area": None,
        "skills": [],
    }
    base.update(overrides)
    return base


def test_schema_accepts_null_accumulation_cols() -> None:
    df = pd.DataFrame([_row(i) for i in range(3)])
    PostingSchema.validate(df, lazy=True)


def test_schema_accepts_populated_accumulation_cols() -> None:
    now = pd.Timestamp(datetime.now(UTC))
    earlier = now - pd.Timedelta(days=30)
    df = pd.DataFrame(
        [
            _row(0, first_seen_at=earlier, last_seen_at=now),
            _row(1, first_seen_at=now, last_seen_at=now),
        ]
    )
    PostingSchema.validate(df, lazy=True)


def test_schema_rejects_when_columns_missing() -> None:
    """Strict mode means both cols MUST exist (nullable or not)."""
    row = _row(0)
    row.pop("first_seen_at")
    row.pop("last_seen_at")
    df = pd.DataFrame([row])
    try:
        PostingSchema.validate(df, lazy=True)
    except Exception:  # pandera.errors.SchemaErrors
        return
    raise AssertionError(
        "PostingSchema is configured strict — frames missing first_seen_at / "
        "last_seen_at must be rejected. fetch_sources + normalise.run inject "
        "the columns as NaT so production paths never trip this."
    )
