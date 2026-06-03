"""Multilingual keyword classifier for `work_arrangement`.

Tiebreak rule: **hybrid > remote > onsite**. Hybrid mentions override
remote hits because hybrid postings frequently advertise "remote
flexibility" that would otherwise misclassify them as full-remote.
"""

from __future__ import annotations

import logging

import pandas as pd

from jobpipe.work_arrangement import keywords

logger = logging.getLogger(__name__)


def _classify(text: str | None, country: str | None) -> str | None:
    if not text:
        return None
    langs = keywords.languages_for_country(country)
    for lang in langs:
        for pattern in keywords.HYBRID.get(lang, []):
            if pattern.search(text):
                return "hybrid"
    for lang in langs:
        for pattern in keywords.REMOTE.get(lang, []):
            if pattern.search(text):
                return "remote"
    for lang in langs:
        for pattern in keywords.ONSITE.get(lang, []):
            if pattern.search(text):
                return "onsite"
    return None


def tag(
    df: pd.DataFrame,
    *,
    lookup: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Populate the `work_arrangement` column.

    `lookup` maps `posting_id` to the full posting description (typically
    sourced from Adzuna's `/v1/api/jobs/{country}/details/{id}` endpoint).
    Rows missing from the lookup fall back to the truncated `description`
    column already present on the frame.

    The scan haystack is `title + " " + body` to catch titles like
    "Senior Analyst (Remote)" without needing the body.

    Rows that already have a non-null `work_arrangement` are passed
    through untouched — supports an idempotent "skip rows we already
    classified last week" mode driven by archive lookup.
    """
    out = df.copy()
    if out.empty:
        return out

    if "work_arrangement" not in out.columns:
        out["work_arrangement"] = pd.Series([None] * len(out), index=out.index, dtype="object")

    titles = out["title"].fillna("").astype(str)
    fallback_desc = (
        out["description"]
        if "description" in out.columns
        else pd.Series([""] * len(out), index=out.index)
    )
    fallback_desc = fallback_desc.fillna("").astype(str)
    countries = (
        out["country"].astype(str)
        if "country" in out.columns
        else pd.Series([""] * len(out), index=out.index)
    )
    posting_ids = (
        out["posting_id"].astype(str)
        if "posting_id" in out.columns
        else pd.Series([""] * len(out), index=out.index)
    )

    existing = out["work_arrangement"]
    classifications: list[str | None] = []
    classified = 0
    for posting_id, title, country, fallback, current in zip(
        posting_ids, titles, countries, fallback_desc, existing, strict=True
    ):
        if pd.notna(current) and current:
            classifications.append(current)
            continue
        body = lookup.get(posting_id) if lookup else None
        if body is None:
            body = fallback
        haystack = f"{title} {body}"
        verdict = _classify(haystack, country)
        if verdict is not None:
            classified += 1
        classifications.append(verdict)

    out["work_arrangement"] = pd.Series(classifications, index=out.index, dtype="object")
    logger.info(
        "work_arrangement: %d / %d postings classified (%.1f%%)",
        classified,
        len(out),
        100.0 * classified / len(out) if len(out) else 0.0,
    )
    return out
