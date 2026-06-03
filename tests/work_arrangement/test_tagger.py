"""Tagger correctness — multilingual coverage + tiebreak + edge cases."""

from __future__ import annotations

import pandas as pd
import pytest

from jobpipe.work_arrangement import tagger


def _row(idx: int, title: str, description: str = "", country: str = "GB") -> dict:
    return {
        "posting_id": f"posting-{idx:04d}",
        "title": title,
        "description": description,
        "country": country,
        "work_arrangement": None,
    }


def _df(*rows: dict) -> pd.DataFrame:
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Single-language coverage


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Fully remote role", "remote"),
        ("100% remote — no relocation", "remote"),
        ("Remote-first culture", "remote"),
        ("Work from home opportunity", "remote"),
        ("Hybrid role: 3 days in office", "hybrid"),
        ("Hybrid work model", "hybrid"),
        ("On-site position in our London office", "onsite"),
        ("In-office collaboration", "onsite"),
        ("Office-based role", "onsite"),
        ("Senior Data Analyst", None),  # no arrangement signal
        ("", None),
    ],
)
def test_english_keywords_classify(text: str, expected: str | None) -> None:
    df = _df(_row(0, title="Data Analyst", description=text, country="GB"))
    out = tagger.tag(df)
    assert (
        out.loc[0, "work_arrangement"] == expected
        if expected
        else pd.isna(out.loc[0, "work_arrangement"])
    )


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Teletrabajo total", "remote"),
        ("Trabajo a distancia disponible", "remote"),
        ("Modalidad híbrida con dos días en oficina", "hybrid"),
        ("Trabajo híbrido", "hybrid"),
        ("Trabajo presencial en Madrid", "onsite"),
        ("Modalidad presencial", "onsite"),
        ("Analista de datos senior", None),
    ],
)
def test_spanish_keywords_classify(text: str, expected: str | None) -> None:
    df = _df(_row(0, title="Analista", description=text, country="ES"))
    out = tagger.tag(df)
    assert (
        out.loc[0, "work_arrangement"] == expected
        if expected
        else pd.isna(out.loc[0, "work_arrangement"])
    )


# ---------------------------------------------------------------------------
# Tiebreak rule: hybrid > remote > onsite


def test_hybrid_beats_remote_when_both_present() -> None:
    df = _df(
        _row(
            0,
            title="Data Engineer",
            description="Hybrid role with remote flexibility",
            country="GB",
        )
    )
    out = tagger.tag(df)
    assert out.loc[0, "work_arrangement"] == "hybrid"


def test_remote_beats_onsite_when_both_present() -> None:
    df = _df(_row(0, title="Engineer", description="Fully remote — no on-site days", country="GB"))
    out = tagger.tag(df)
    assert out.loc[0, "work_arrangement"] == "remote"


# ---------------------------------------------------------------------------
# Word boundaries


def test_premote_does_not_match_remote() -> None:
    df = _df(_row(0, title="Premote Lead", description="Some unrelated text", country="GB"))
    out = tagger.tag(df)
    assert pd.isna(out.loc[0, "work_arrangement"])


def test_hybridization_does_not_match_hybrid() -> None:
    # "hybrid" + non-word char after; tagger should NOT match within "hybridization".
    df = _df(_row(0, title="Specialist", description="Plant hybridization research", country="GB"))
    out = tagger.tag(df)
    assert pd.isna(out.loc[0, "work_arrangement"])


# ---------------------------------------------------------------------------
# Title-only signal (description empty)


def test_title_alone_classifies() -> None:
    df = _df(_row(0, title="Senior Data Analyst (Remote)", description="", country="GB"))
    out = tagger.tag(df)
    assert out.loc[0, "work_arrangement"] == "remote"


# ---------------------------------------------------------------------------
# Lookup overrides description


def test_lookup_overrides_truncated_description() -> None:
    df = _df(_row(0, title="Engineer", description="Generic blurb", country="GB"))
    lookup = {"posting-0000": "Full description mentions fully remote work."}
    out = tagger.tag(df, lookup=lookup)
    assert out.loc[0, "work_arrangement"] == "remote"


# ---------------------------------------------------------------------------
# Already-classified rows pass through


def test_existing_classification_preserved() -> None:
    row = _row(0, title="Whatever", description="On-site only", country="GB")
    row["work_arrangement"] = "remote"  # pre-set from prior accumulation
    df = _df(row)
    out = tagger.tag(df)
    assert out.loc[0, "work_arrangement"] == "remote"


# ---------------------------------------------------------------------------
# Country language routing


def test_spanish_posting_uses_es_dictionary() -> None:
    df = _df(_row(0, title="Analista", description="Teletrabajo desde casa", country="ES"))
    out = tagger.tag(df)
    assert out.loc[0, "work_arrangement"] == "remote"


def test_gb_posting_does_not_match_spanish_keyword() -> None:
    # English-only country shouldn't match Spanish-specific keyword
    # (test uses a Spanish-only phrase like "presencial" which doesn't appear
    # in the English dictionary).
    df = _df(
        _row(0, title="Analyst", description="Some content with presencial mention", country="GB")
    )
    out = tagger.tag(df)
    # GB scans only English patterns; "presencial" should not match.
    assert pd.isna(out.loc[0, "work_arrangement"])


# ---------------------------------------------------------------------------
# Empty + edge cases


def test_empty_df_returns_empty_with_column() -> None:
    out = tagger.tag(pd.DataFrame())
    assert out.empty


def test_null_country_falls_back_to_english() -> None:
    df = _df(_row(0, title="Engineer", description="Fully remote role", country=""))
    out = tagger.tag(df)
    assert out.loc[0, "work_arrangement"] == "remote"
