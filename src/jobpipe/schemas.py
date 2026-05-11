"""Pandera schemas — the contract between adapters and the rest of the pipeline.

Strict mode is active from P2 onward; ``BenchmarkSchema`` is still relaxed
until benchmark adapters land in P4.
"""

from __future__ import annotations

import pandera.pandas as pa
from pandera.typing import Series


class PostingSchema(pa.DataFrameModel):
    """Normalised job posting. Adapters MUST emit DataFrames conforming to this."""

    posting_id: Series[str] = pa.Field(nullable=False, unique=True)
    source: Series[str] = pa.Field(nullable=False)
    title: Series[str] = pa.Field(nullable=False, str_length={"min_value": 1, "max_value": 500})
    company: Series[str] = pa.Field(nullable=True)
    location_raw: Series[str] = pa.Field(nullable=True)
    country: Series[str] = pa.Field(nullable=False, str_length={"min_value": 2, "max_value": 2})
    region: Series[str] = pa.Field(nullable=True)
    remote: Series[bool] = pa.Field(nullable=True)

    salary_min_eur: Series[float] = pa.Field(nullable=True, ge=0, le=1e7)
    salary_max_eur: Series[float] = pa.Field(nullable=True, ge=0, le=1e7)
    salary_period: Series[str] = pa.Field(
        nullable=True,
        isin=["annual", "monthly", "weekly", "daily", "hourly"],
    )
    salary_annual_eur_p50: Series[float] = pa.Field(nullable=True, ge=0, le=1e7)
    salary_imputed: Series[bool] = pa.Field(nullable=True)

    posted_at: Series[pa.DateTime] = pa.Field(nullable=False)
    ingested_at: Series[pa.DateTime] = pa.Field(nullable=False)
    posting_url: Series[str] = pa.Field(nullable=False, str_startswith="http")

    isco_code: Series[str] = pa.Field(nullable=True, str_matches=r"^\d{4}$")
    isco_match_method: Series[str] = pa.Field(
        nullable=True,
        isin=["exact", "fuzzy", "llm", "none"],
    )
    isco_match_score: Series[float] = pa.Field(nullable=True, ge=0.0, le=1.0)

    raw_payload: Series[str] = pa.Field(nullable=True)

    class Config:
        strict = True
        coerce = True


class BenchmarkSchema(pa.DataFrameModel):
    """Official salary benchmark row. Pre-converted to EUR via fx.py."""

    isco_code: Series[str] = pa.Field(nullable=False, str_matches=r"^\d{4}$")
    country: Series[str] = pa.Field(nullable=False, str_length={"min_value": 2, "max_value": 2})
    period: Series[str] = pa.Field(nullable=False)  # e.g. "2024-Q4" or "2024"
    currency: Series[str] = pa.Field(nullable=False)
    median_eur: Series[float] = pa.Field(nullable=False, ge=0, le=1e7)
    p25_eur: Series[float] = pa.Field(nullable=True, ge=0, le=1e7)
    p75_eur: Series[float] = pa.Field(nullable=True, ge=0, le=1e7)
    n_observations: Series[int] = pa.Field(nullable=True, ge=0)
    source: Series[str] = pa.Field(nullable=False)
    source_url: Series[str] = pa.Field(nullable=False, str_startswith="http")
    retrieved_at: Series[pa.DateTime] = pa.Field(nullable=False)

    class Config:
        strict = False
        coerce = True
