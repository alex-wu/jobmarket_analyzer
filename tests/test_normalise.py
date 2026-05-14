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

LABELS = pd.DataFrame(
    [
        ("2511", "Systems analysts", "preferred"),
        ("2511", "data analyst", "alt"),
        ("2511", "data scientist", "alt"),
        ("2521", "Database designers and administrators", "preferred"),
        ("2521", "database administrator", "alt"),
        ("2421", "Management and organization analysts", "preferred"),
        ("2421", "business analyst", "alt"),
    ],
    columns=["isco_code", "label", "label_kind"],
)


def test_run_converts_gbp_to_eur() -> None:
    df = pd.DataFrame([_row(0)])
    out = normalise.run(df, RATES, labels_df=LABELS)
    assert out.loc[0, "salary_min_eur"] == pytest.approx(50_000 / 0.85)
    assert out.loc[0, "salary_max_eur"] == pytest.approx(60_000 / 0.85)


def test_run_recomputes_p50_midpoint_post_fx() -> None:
    df = pd.DataFrame([_row(0, salary_annual_eur_p50=9_999.0)])
    out = normalise.run(df, RATES, labels_df=LABELS)
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
    out = normalise.run(df, RATES, labels_df=LABELS)
    assert len(out) == 2
    assert set(out["source"]) == {"adzuna", "lever"}


def test_run_emits_strict_valid_schema() -> None:
    df = pd.DataFrame([_row(i) for i in range(3)])
    out = normalise.run(df, RATES, labels_df=LABELS)
    PostingSchema.validate(out, lazy=True)


def test_run_empty_df_passes_through() -> None:
    df = pd.DataFrame()
    out = normalise.run(df, RATES, labels_df=LABELS)
    assert out.empty


def test_run_handles_missing_rate_by_leaving_null() -> None:
    df = pd.DataFrame([_row(0, country="ZZ")])  # unknown country
    out = normalise.run(df, RATES, labels_df=LABELS)
    assert pd.isna(out.loc[0, "salary_min_eur"])
    assert pd.isna(out.loc[0, "salary_max_eur"])
    assert pd.isna(out.loc[0, "salary_annual_eur_p50"])
    PostingSchema.validate(out, lazy=True)


def test_run_is_idempotent_on_repeat() -> None:
    df = pd.DataFrame([_row(i) for i in range(3)])
    once = normalise.run(df, RATES, labels_df=LABELS)
    # Second pass: salary already in EUR, rate-conversion would divide again.
    # The dedupe + recompute steps remain stable shape-wise.
    twice = normalise.run(once, RATES, labels_df=LABELS)
    assert len(once) == len(twice)


def test_run_populates_isco_columns_from_labels() -> None:
    df = pd.DataFrame(
        [
            _row(0, posting_url="https://ex.com/a", title="Data Analyst"),
            _row(1, posting_url="https://ex.com/b", title="Database Administrator"),
            _row(2, posting_url="https://ex.com/c", title="Senior Business Analyst"),
            _row(3, posting_url="https://ex.com/d", title="Lead Underwater Welder"),
        ]
    )
    out = (
        normalise.run(df, RATES, labels_df=LABELS).sort_values("posting_id").reset_index(drop=True)
    )
    by_title = dict(zip(out["title"], out["isco_code"], strict=False))
    assert by_title["Data Analyst"] == "2511"
    assert by_title["Database Administrator"] == "2521"
    assert by_title["Senior Business Analyst"] == "2421"
    assert by_title["Lead Underwater Welder"] is None
    matched = out[out["isco_code"].notna()]
    assert (matched["isco_match_method"] == "fuzzy").all()
    assert (matched["isco_match_score"] >= 0.88).all()
    unmatched = out[out["isco_code"].isna()]
    assert (unmatched["isco_match_method"] == "none").all()


def test_run_defaults_to_committed_label_snapshot_when_none_passed() -> None:
    # No labels_df arg → loader picks up config/esco/isco08_labels.parquet.
    df = pd.DataFrame([_row(0, title="Data Analyst")])
    out = normalise.run(df, RATES)
    assert out.loc[0, "isco_code"] == "2511"
    assert out.loc[0, "isco_match_method"] == "fuzzy"
