"""Pure normalisation step. DataFrames in, DataFrames out. No HTTP, no FS, no DB.

Pipeline (P2):

1. Convert native-currency salary fields → EUR using a rates dict
   (loaded once at the CLI boundary by :mod:`jobpipe.fx`).
2. Recompute ``salary_annual_eur_p50`` as the midpoint of the post-FX
   min/max; the adapter-set value is in native currency and is
   therefore stale after step 1.
3. Cross-source dedupe: sha1 of normalised URL, fallback to
   sha1(title+company+country).
4. Validate against the strict :class:`PostingSchema`.

ISCO tagging lands in P4 and slots in before the schema validation.
"""

from __future__ import annotations

import logging

import pandas as pd

from jobpipe import dedupe, fx
from jobpipe.schemas import PostingSchema

logger = logging.getLogger(__name__)


def run(raw: pd.DataFrame, rates: dict[str, float]) -> pd.DataFrame:
    """Normalise a raw postings DataFrame.

    Returns a frame validated against ``PostingSchema`` (strict).
    """
    if raw.empty:
        return raw.copy()

    df = fx.convert_to_eur(raw, rates)
    df = _recompute_p50(df)
    df = dedupe.cross_source(df)
    PostingSchema.validate(df, lazy=True)
    return df


def _recompute_p50(df: pd.DataFrame) -> pd.DataFrame:
    """Replace ``salary_annual_eur_p50`` with midpoint of min/max (post-FX).

    v1 sources (Adzuna) emit ``salary_period = 'annual'`` from the adapter,
    so no period conversion is needed yet. Future adapters that emit
    monthly/hourly etc. must annualise before reaching this function.
    """
    out = df.copy()
    out["salary_annual_eur_p50"] = (out["salary_min_eur"] + out["salary_max_eur"]) / 2
    return out
