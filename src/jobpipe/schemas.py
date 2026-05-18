"""Pandera schemas — the contract between adapters and the rest of the pipeline.

Strict mode is active on both schemas from P4 onward (the third benchmark
adapter landed in P4, so the relaxation flag was retired).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pandera.pandas as pa
from pandera.typing import Series


_ACCUMULATION_COLS = ("first_seen_at", "last_seen_at")


def _is_list_of_str_or_null(v: object) -> bool:
    """Accept None, NaN, list[str], or numpy/pyarrow array of strings.

    pyarrow round-trips list-typed parquet cells as np.ndarray, so the strict
    `isinstance(v, list)` check would reject every frame loaded back from
    disk. Both list and ndarray are valid wire shapes for our consumers.
    """
    if v is None:
        return True
    if isinstance(v, (list, np.ndarray)):
        return all(isinstance(x, str) for x in v)
    try:
        if pd.isna(v):
            return True
    except (TypeError, ValueError):
        pass
    return False

# Source-optional columns: Adzuna populates these per posting; other adapters
# (Greenhouse, Lever, Ashby, ...) leave them unset. The injection helper fills
# missing-column cases with all-null Series so the strict PostingSchema accepts
# frames from sources that don't have them.
_SOURCE_OPTIONAL_OBJECT_COLS = (
    "adzuna_category",
    "contract_type",
    "contract_time",
    "description",
    "location_area",
    "skills",
)


def inject_accumulation_cols(df: pd.DataFrame) -> pd.DataFrame:
    """Inject pipeline-injected and source-optional columns as null when missing.

    Two flavours of null injection live here:

    - **ADR-020 accumulation cols** (`first_seen_at`, `last_seen_at`): tz-aware
      NaT. Per-source adapters MUST NOT populate these; export_accumulated()
      is the sole producer of non-null values. Tz-aware so DuckDB's COALESCE
      in export_accumulated doesn't error on mixed-tz inputs.

    - **Source-optional cols** (Adzuna's category/contract/description/area):
      object-dtype None. Adzuna populates them at adapter time; other adapters
      leave them unset, so this injection lets non-Adzuna frames pass the
      strict PostingSchema validation.

    Exported so adapter smoke tests can mirror the production injection point
    when calling `PostingSchema.validate(...)` directly.
    """
    if df.empty:
        return df
    out = df
    for col in _ACCUMULATION_COLS:
        if col not in out.columns:
            out = out.assign(
                **{col: pd.Series(pd.NaT, index=out.index, dtype="datetime64[ns, UTC]")}
            )
    for col in _SOURCE_OPTIONAL_OBJECT_COLS:
        if col not in out.columns:
            out = out.assign(**{col: pd.Series([None] * len(out), dtype="object")})
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

    adzuna_category: Series[str] = pa.Field(nullable=True)
    contract_type: Series[str] = pa.Field(
        nullable=True,
        isin=["permanent", "contract"],
    )
    contract_time: Series[str] = pa.Field(
        nullable=True,
        isin=["full_time", "part_time"],
    )
    description: Series[str] = pa.Field(
        nullable=True,
        str_length={"max_value": 600},
    )
    # Object-dtype list[str]. Pandera has no native list dtype; adapters MUST
    # emit list[str] or None. The class-level @pa.check below enforces it.
    location_area: Series[object] = pa.Field(nullable=True)
    # Populated by jobpipe.skills.tagger in normalise.run after ISCO matching.
    # Empty list = matched-nothing (non-null); None only for pre-PR2b legacy frames.
    skills: Series[object] = pa.Field(nullable=True)

    class Config:
        strict = True
        coerce = True

    @pa.check("location_area", name="location_area_is_list_of_str")
    def _check_location_area(cls, series: pd.Series) -> pd.Series:
        return series.map(_is_list_of_str_or_null)

    @pa.check("skills", name="skills_is_list_of_str")
    def _check_skills(cls, series: pd.Series) -> pd.Series:
        return series.map(_is_list_of_str_or_null)


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
