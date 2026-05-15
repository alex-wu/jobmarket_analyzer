"""Fuzzy-match posting titles to ISCO-08 4-digit codes via rapidfuzz.

Pure: DataFrames in, DataFrames out. No HTTP, no FS.

Output columns written onto the input frame:

* ``isco_code`` (str | None) — 4-digit ISCO-08 group
* ``isco_match_method`` (str | None) — ``"fuzzy"`` on hit, ``"none"`` on miss
* ``isco_match_score`` (float | None) — 0.0..1.0 (rapidfuzz score / 100)

Strategy: ``rapidfuzz.process.extractOne`` with ``token_set_ratio`` and a
score cutoff of 85. ADR-006 set this at 88; lowered to 85 after Run 2 of
``refresh.yml`` measured a 55.75% live match rate at n=504 (under the 60%
ADR-013 threshold). See ``docs/open-questions.md`` for the re-measure plan.
Raise for stricter joins, lower for higher coverage at the cost of false
positives.

The matcher trusts the strict ``PostingSchema``: ``title`` is non-null. NaN
titles still survive matching as a no-match row to keep this safe under the
relaxed pre-validate frame the runner hands in.
"""

from __future__ import annotations

import re

import pandas as pd
from rapidfuzz import fuzz, process

DEFAULT_SCORE_CUTOFF = 85

_PARENTHETICAL_RE = re.compile(r"\([^)]*\)")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9\s]+")
_WHITESPACE_RE = re.compile(r"\s+")


def _clean_title(raw: object) -> str:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return ""
    text = str(raw).lower()
    text = _PARENTHETICAL_RE.sub(" ", text)
    text = _NON_ALNUM_RE.sub(" ", text)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    return text


def _build_lookup(labels_df: pd.DataFrame) -> tuple[list[str], list[str]]:
    """Return ``(candidates, candidate_to_code)`` aligned by index."""
    candidates: list[str] = []
    codes: list[str] = []
    for isco_code, label in zip(
        labels_df["isco_code"].astype(str),
        labels_df["label"].astype(str),
        strict=False,
    ):
        cleaned = _clean_title(label)
        if not cleaned:
            continue
        candidates.append(cleaned)
        codes.append(isco_code)
    return candidates, codes


def tag(
    df: pd.DataFrame,
    labels_df: pd.DataFrame,
    *,
    score_cutoff: int = DEFAULT_SCORE_CUTOFF,
) -> pd.DataFrame:
    """Populate ISCO columns on ``df`` from ``labels_df``.

    Returns a new DataFrame; the input is not mutated. Existing ``isco_code``
    values on the input are overwritten (the pipeline calls this once per
    normalise run; adapters always emit ``isco_code=None``).
    """
    out = df.copy()

    if labels_df.empty:
        out["isco_code"] = pd.Series([None] * len(out), dtype="object")
        out["isco_match_method"] = pd.Series(
            ["none"] * len(out) if len(out) else [], dtype="object"
        )
        out["isco_match_score"] = pd.Series([None] * len(out), dtype="object")
        return out

    if out.empty:
        out["isco_code"] = pd.Series([], dtype="object")
        out["isco_match_method"] = pd.Series([], dtype="object")
        out["isco_match_score"] = pd.Series([], dtype="object")
        return out

    candidates, codes = _build_lookup(labels_df)
    if not candidates:
        out["isco_code"] = None
        out["isco_match_method"] = "none"
        out["isco_match_score"] = None
        return out

    isco_codes: list[str | None] = []
    methods: list[str] = []
    scores: list[float | None] = []

    for raw_title in out["title"].tolist():
        cleaned = _clean_title(raw_title)
        if not cleaned:
            isco_codes.append(None)
            methods.append("none")
            scores.append(None)
            continue
        match = process.extractOne(
            cleaned,
            candidates,
            scorer=fuzz.token_set_ratio,
            score_cutoff=score_cutoff,
        )
        if match is None:
            isco_codes.append(None)
            methods.append("none")
            scores.append(None)
        else:
            _label, score, idx = match
            isco_codes.append(codes[idx])
            methods.append("fuzzy")
            scores.append(round(float(score) / 100.0, 4))

    out["isco_code"] = pd.Series(isco_codes, index=out.index, dtype="object")
    out["isco_match_method"] = pd.Series(methods, index=out.index, dtype="object")
    out["isco_match_score"] = pd.Series(scores, index=out.index, dtype="object")
    return out
