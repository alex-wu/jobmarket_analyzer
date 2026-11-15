"""Pure normalisation step. DataFrames in, DataFrames out. No HTTP, no FS, no DB.

Pipeline:

1. Convert native-currency salary fields → EUR using a rates dict
   (loaded once at the CLI boundary by :mod:`jobpipe.fx`).
2. Recompute ``salary_annual_eur_p50`` as the midpoint of the post-FX
   min/max; the adapter-set value is in native currency and is
   therefore stale after step 1.
   Then blank salaries below the preset's ``salary_floor_eur`` (see
   :func:`apply_salary_floor`).
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
from jobpipe.schemas import SALARY_COLUMNS, PostingSchema, inject_accumulation_cols
from jobpipe.skills import tagger as skills_tagger
from jobpipe.work_arrangement import tagger as work_arrangement_tagger

logger = logging.getLogger(__name__)


def run(
    raw: pd.DataFrame,
    rates: dict[str, float],
    labels_df: pd.DataFrame | None = None,
    *,
    skills_df: pd.DataFrame | None = None,
    focus_isco: list[str] | None = None,
    since_days: int | None = None,
    salary_floor_eur: float | None = None,
    work_arrangement_lookup: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Normalise a raw postings DataFrame.

    ``labels_df`` is the ESCO ISCO-08 label snapshot. If ``None``, the
    default committed parquet is loaded from disk — convenient for the
    CLI path, but tests should pass an explicit frame to keep this pure.

    ``since_days`` applies a canonical recency floor: rows with ``posted_at``
    older than ``now - since_days`` are dropped before dedupe. This is the
    source-agnostic guarantee — adapter-level knobs (e.g. Adzuna's
    ``max_days_old``) are bandwidth optimisations layered on top of it.

    ``salary_floor_eur`` blanks implausibly low annual salaries — see
    :func:`apply_salary_floor`. ``None`` disables the floor.

    Returns a frame validated against ``PostingSchema`` (strict).
    """
    if raw.empty:
        return raw.copy()

    df = fx.convert_to_eur(raw, rates)
    df = _recompute_p50(df)
    df = apply_salary_floor(df, salary_floor_eur)

    if since_days is not None:
        floor = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=since_days)
        pre_filter = len(df)
        df = df[df["posted_at"] >= floor].reset_index(drop=True)
        logger.info(
            "recency: %d → %d postings after since_days=%d filter",
            pre_filter,
            len(df),
            since_days,
        )

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

    if skills_df is not None:
        df = skills_tagger.tag(df, skills_df, focus_isco=focus_isco)

    df = work_arrangement_tagger.tag(df, lookup=work_arrangement_lookup)

    df = dedupe.cross_source(df)
    df = inject_accumulation_cols(df)
    PostingSchema.validate(df, lazy=True)
    return df


def _recompute_p50(df: pd.DataFrame) -> pd.DataFrame:
    """Replace ``salary_annual_eur_p50`` with midpoint of min/max (post-FX).

    v1 sources (Adzuna) emit ``salary_period = 'annual'`` from the adapter,
    so no period conversion is needed yet. Future adapters that emit
    monthly/hourly etc. must annualise before reaching this function.
    """
    out = df.copy()
    out["salary_annual_eur_p50"] = ((out["salary_min_eur"] + out["salary_max_eur"]) / 2).round(2)
    return out


def apply_salary_floor(df: pd.DataFrame, floor_eur: float | None) -> pd.DataFrame:
    """Blank the salary of postings whose annual EUR midpoint is below ``floor_eur``.

    Adzuna returns ``salary_min`` / ``salary_max`` with no pay period and the
    adapter labels every value ``annual``. Ads that quote a day rate, an
    hourly rate or a monthly salary therefore arrive as "annual" salaries of
    a few euros to a few thousand. The true period cannot be recovered
    reliably, so the salary is treated as not stated: every column in
    :data:`jobpipe.schemas.SALARY_COLUMNS` is set to null and the posting itself is kept (it
    still counts for volume, skills and work arrangement). The original
    figures stay in ``raw_payload``.

    ``None`` leaves the frame untouched.
    """
    if floor_eur is None:
        return df
    below = df["salary_annual_eur_p50"] < floor_eur
    n_below = int(below.sum())
    if n_below == 0:
        return df
    out = df.copy()
    for col in SALARY_COLUMNS:
        if pd.api.types.is_float_dtype(out[col]):
            out.loc[below, col] = float("nan")
        else:
            # bool / str columns: go through object so None is storable.
            out[col] = out[col].astype(object)
            out.loc[below, col] = None
    logger.info(
        "salary floor: blanked %d of %d salaries below EUR %s per year",
        n_below,
        int(df["salary_annual_eur_p50"].notna().sum()),
        f"{floor_eur:,.0f}",
    )
    return out
