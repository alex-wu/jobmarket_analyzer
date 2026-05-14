"""Pure normalisation step. DataFrames in, DataFrames out. No HTTP, no FS, no DB.

Pipeline:

1. Convert native-currency salary fields → EUR using a rates dict
   (loaded once at the CLI boundary by :mod:`jobpipe.fx`).
2. Recompute ``salary_annual_eur_p50`` as the midpoint of the post-FX
   min/max; the adapter-set value is in native currency and is
   therefore stale after step 1.
3. ISCO-08 tagging via rapidfuzz against the static ESCO snapshot
   (P4). The label frame is injected by the caller; when ``None``
   the loader falls back to the committed parquet.
4. Cross-source dedupe: sha1 of normalised URL, fallback to
   sha1(title+company+country).
5. Validate against the strict :class:`PostingSchema`.
"""

from __future__ import annotations

import logging

import pandas as pd

from jobpipe import dedupe, fx
from jobpipe.isco import loader as isco_loader
from jobpipe.isco import tagger as isco_tagger
from jobpipe.schemas import PostingSchema

logger = logging.getLogger(__name__)


def run(
    raw: pd.DataFrame,
    rates: dict[str, float],
    labels_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Normalise a raw postings DataFrame.

    ``labels_df`` is the ESCO ISCO-08 label snapshot. If ``None``, the
    default committed parquet is loaded from disk — convenient for the
    CLI path, but tests should pass an explicit frame to keep this pure.

    Returns a frame validated against ``PostingSchema`` (strict).
    """
    if raw.empty:
        return raw.copy()

    df = fx.convert_to_eur(raw, rates)
    df = _recompute_p50(df)

    labels = isco_loader.load_isco_labels() if labels_df is None else labels_df
    pre_match = len(df)
    df = isco_tagger.tag(df, labels)
    matched = int(df["isco_code"].notna().sum())
    logger.info(
        "isco: %d / %d postings matched (%.1f%%)",
        matched,
        pre_match,
        100.0 * matched / pre_match if pre_match else 0.0,
    )

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
