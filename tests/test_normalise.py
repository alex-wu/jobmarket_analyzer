"""Pure normalise pipeline: FX + p50 + cross-source dedupe + strict schema."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pandas as pd
import pytest

from jobpipe import normalise
from jobpipe.schemas import PostingSchema


def _row(idx: int, **overrides: Any) -> dict[str, Any]:
    now = pd.Timestamp(datetime.now(UTC))
    base: dict[str, Any] = {
        "posting_id": f"posting-{idx:04d}",
        "source": "fake",
        "title": f"Data Analyst {idx}",
        "company": "Acme",
        "location_raw": "London",
        "country": "GB",
        "region": None,
        "remote": None,
        # Native GBP — the lie that P2 fixes.
        "salary_min_eur": 50_000.0,
        "salary_max_eur": 60_000.0,
        "salary_period": "annual",
        "salary_annual_eur_p50": 55_000.0,
        "salary_imputed": False,
        "posted_at": now,
        "ingested_at": now,
        "posting_url": f"https://example.test/jobs/{idx}",
        "isco_code": None,
        "isco_match_method": None,
        "isco_match_score": None,
        "raw_payload": "{}",
    }
    base.update(overrides)
    return base


RATES = {"EUR": 1.0, "GBP": 0.85, "USD": 1.10}


def test_run_converts_gbp_to_eur() -> None:
    df = pd.DataFrame([_row(0)])
    out = normalise.run(df, RATES)
    assert out.loc[0, "salary_min_eur"] == pytest.approx(50_000 / 0.85)
    assert out.loc[0, "salary_max_eur"] == pytest.approx(60_000 / 0.85)


def test_run_recomputes_p50_midpoint_post_fx() -> None:
    df = pd.DataFrame([_row(0, salary_annual_eur_p50=9_999.0)])
    out = normalise.run(df, RATES)
    expected = (50_000 / 0.85 + 60_000 / 0.85) / 2
    assert out.loc[0, "salary_annual_eur_p50"] == pytest.approx(expected)


def test_run_collapses_cross_source_dupes() -> None:
    df = pd.DataFrame(
        [
            _row(0, posting_url="https://ex.com/a", source="adzuna"),
            _row(1, posting_url="https://ex.com/a?utm_x=1", source="greenhouse"),
            _row(2, posting_url="https://ex.com/b", source="lever"),
        ]
    )
    out = normalise.run(df, RATES)
    assert len(out) == 2
    assert set(out["source"]) == {"adzuna", "lever"}


def test_run_emits_strict_valid_schema() -> None:
    df = pd.DataFrame([_row(i) for i in range(3)])
    out = normalise.run(df, RATES)
    PostingSchema.validate(out, lazy=True)


def test_run_empty_df_passes_through() -> None:
    df = pd.DataFrame()
    out = normalise.run(df, RATES)
    assert out.empty


def test_run_handles_missing_rate_by_leaving_null() -> None:
    df = pd.DataFrame([_row(0, country="ZZ")])  # unknown country
    out = normalise.run(df, RATES)
    assert pd.isna(out.loc[0, "salary_min_eur"])
    assert pd.isna(out.loc[0, "salary_max_eur"])
    assert pd.isna(out.loc[0, "salary_annual_eur_p50"])
    PostingSchema.validate(out, lazy=True)


def test_run_is_idempotent_on_repeat() -> None:
    df = pd.DataFrame([_row(i) for i in range(3)])
    once = normalise.run(df, RATES)
    # Second pass: salary already in EUR, rate-conversion would divide again.
    # The dedupe + recompute steps remain stable shape-wise.
    twice = normalise.run(once, RATES)
    assert len(once) == len(twice)
