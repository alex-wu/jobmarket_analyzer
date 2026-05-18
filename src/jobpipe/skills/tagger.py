"""ESCO skill extraction via Aho-Corasick multi-keyword scan.

Adds a `skills: list[str]` column to a PostingSchema-shaped DataFrame.
Each value is a sorted list of ESCO `preferred_label`s whose preferred or
alternative label appears in `title + description` with word-boundary anchors.

Deterministic, no LLM, no network. The Aho-Corasick automaton scans in
O(haystack_len + matches), which is the only viable shape at the 13k+ ESCO
Pillar B label-set size — a Python regex alternation over that many patterns
backtracks catastrophically.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

import ahocorasick
import pandas as pd

logger = logging.getLogger(__name__)

_WORD_CHARS = set("abcdefghijklmnopqrstuvwxyz0123456789_")


def _build_automaton(skills_df: pd.DataFrame) -> ahocorasick.Automaton:
    """One automaton per call. Keys are lowercased; values are preferred_labels."""
    auto = ahocorasick.Automaton()
    for row in skills_df.itertuples(index=False):
        preferred = (row.preferred_label or "").strip()
        if not preferred:
            continue
        keys = [preferred]
        alts = getattr(row, "alt_labels", None)
        if alts is not None:
            for alt in _iter_strs(alts):
                alt = alt.strip()
                if alt:
                    keys.append(alt)
        for k in keys:
            kl = k.lower()
            if len(kl) < 2:
                continue
            existing = auto.get(kl, None)
            # When two different skills share an alt label, keep the first to
            # win — both are real matches but reporting duplicates muddies the
            # output. The tagger output dedupes after matching anyway.
            if existing is None:
                auto.add_word(kl, (kl, preferred))
    auto.make_automaton()
    return auto


def _iter_strs(value: object) -> Iterable[str]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    try:
        return [str(v) for v in value]
    except TypeError:
        return ()


def _is_word_char(ch: str) -> bool:
    return ch.lower() in _WORD_CHARS


def _word_boundary_match(haystack: str, end_idx: int, key_len: int) -> bool:
    """Aho-Corasick yields substring hits; enforce \\b on both sides."""
    start = end_idx - key_len + 1
    if start > 0 and _is_word_char(haystack[start - 1]):
        return False
    after = end_idx + 1
    return not (after < len(haystack) and _is_word_char(haystack[after]))


def tag(
    df: pd.DataFrame,
    skills_df: pd.DataFrame,
    *,
    focus_isco: list[str] | None = None,
) -> pd.DataFrame:
    """Add a `skills: list[str]` column. Rows with no matches get `[]`.

    When `focus_isco` is set, the skills dictionary is filtered to entries
    whose `related_isco_codes` intersects `focus_isco` BEFORE building the
    automaton — drops off-domain ESCO skills that share generic English words
    with the target role family (e.g. "packaging engineering", "journalism"
    for a data-analyst preset). Skills with no ISCO links at all are dropped
    too, since we have no way to verify their domain relevance.
    """
    if df.empty:
        out = df.copy()
        out["skills"] = pd.Series([], dtype="object")
        return out

    if focus_isco:
        focus_set = set(focus_isco)
        before = len(skills_df)

        def _overlaps(codes: object) -> bool:
            if codes is None:
                return False
            try:
                return any(c in focus_set for c in codes)
            except TypeError:
                return False

        skills_df = skills_df[
            skills_df["related_isco_codes"].map(_overlaps)
        ].reset_index(drop=True)
        logger.info(
            "skills: focus_isco=%s filtered dictionary %d -> %d",
            sorted(focus_set),
            before,
            len(skills_df),
        )

    auto = _build_automaton(skills_df)
    titles = df["title"].fillna("").astype(str)
    descriptions = df.get("description")
    if descriptions is None:
        descriptions = pd.Series([""] * len(df), index=df.index)
    descriptions = descriptions.fillna("").astype(str)

    results: list[list[str]] = []
    for title, desc in zip(titles, descriptions, strict=True):
        haystack = f"{title} {desc}".lower()
        hits: set[str] = set()
        for end_idx, (kl, preferred) in auto.iter(haystack):
            if _word_boundary_match(haystack, end_idx, len(kl)):
                hits.add(preferred)
        results.append(sorted(hits))

    out = df.copy()
    out["skills"] = pd.Series(results, index=df.index, dtype="object")
    matched = sum(1 for r in results if r)
    logger.info(
        "skills: %d / %d postings tagged (%.1f%%) using %d ESCO labels",
        matched,
        len(results),
        100.0 * matched / len(results) if results else 0.0,
        len(skills_df),
    )
    return out
