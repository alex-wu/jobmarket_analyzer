"""Pandera schemas — the contract between adapters and the rest of the pipeline.

Strict mode is active on both schemas from P4 onward (the third benchmark
adapter landed in P4, so the relaxation flag was retired).
"""

from __future__ import annotations

import pandas as pd
import pandera.pandas as pa
from pandera.typing import Series


_ACCUMULATION_COLS = ("first_seen_at", "last_seen_at")


def inject_accumulation_cols(df: pd.DataFrame) -> pd.DataFrame:
    """Inject ADR-020 accumulation cols (first/last_seen_at) as null when missing.

    Per-source adapters MUST NOT populate these — fetch_sources / normalise.run
    inject them as tz-aware NaT before strict validation; export_accumulated()
    is the sole producer of non-null values. This helper is exported so adapter
    smoke tests that call PostingSchema.validate() directly can mirror the
    production injection point.

    Columns are tz-aware (datetime64[ns, UTC]) so the resulting parquet's
    column type matches ingested_at — DuckDB's COALESCE in export_accumulated
    refuses mixed-tz inputs without an explicit cast.
    """
    if df.empty:
        return df
    out = df
    for col in _ACCUMULATION_COLS:
        if col not in out.columns:
            out = out.assign(
                **{col: pd.Series(pd.NaT, index=out.index, dtype="datetime64[ns, UTC]")}
            )
    return out


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
    # ADR-020 accumulation cols. Per-source / per-run frames leave both NaT;
    # duckdb_io.export_accumulated() is the sole producer of non-null values.
    first_seen_at: Series[pa.DateTime] = pa.Field(nullable=True)
    last_seen_at: Series[pa.DateTime] = pa.Field(nullable=True)
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
        strict = True
        coerce = True
