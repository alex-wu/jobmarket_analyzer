"""Unit tests for `jobpipe.skills.tagger`. Pure in-memory, no I/O."""

from __future__ import annotations

import pandas as pd

from jobpipe.skills.tagger import tag


def _skills(
    rows: list[tuple[str, list[str]]],
    iscos: list[list[str]] | None = None,
) -> pd.DataFrame:
    """Build a minimal skills_df fixture: (preferred_label, alt_labels)."""
    iscos_list = iscos or [[] for _ in rows]
    return pd.DataFrame(
        [
            {
                "skill_uri": f"http://example.test/skill/{i}",
                "preferred_label": pref,
                "alt_labels": alts,
                "skill_type": "skill/competence",
                "reuse_level": "cross-sector",
                "related_isco_codes": iscos_list[i],
            }
            for i, (pref, alts) in enumerate(rows)
        ]
    )


def _postings(rows: list[tuple[str, str]]) -> pd.DataFrame:
    return pd.DataFrame([{"title": t, "description": d} for t, d in rows])


def test_matches_preferred_label_in_title() -> None:
    skills = _skills([("SQL", [])])
    df = _postings([("SQL Developer", "")])
    out = tag(df, skills)
    assert out.loc[0, "skills"] == ["SQL"]


def test_matches_alt_label_in_description() -> None:
    skills = _skills([("Python (computer programming)", ["python3", "py3k"])])
    df = _postings([("Backend Engineer", "We use Python3 and Django")])
    out = tag(df, skills)
    assert out.loc[0, "skills"] == ["Python (computer programming)"]


def test_multi_word_match() -> None:
    skills = _skills([("data analysis", [])])
    df = _postings([("Analyst", "You will perform data analysis on customer logs")])
    out = tag(df, skills)
    assert out.loc[0, "skills"] == ["data analysis"]


def test_word_boundary_negative_java_not_in_javascript() -> None:
    skills = _skills([("Java", []), ("JavaScript", [])])
    df = _postings([("Frontend role", "We use JavaScript heavily")])
    out = tag(df, skills)
    assert out.loc[0, "skills"] == ["JavaScript"]


def test_word_boundary_negative_sql_not_in_postgresql() -> None:
    skills = _skills([("SQL", [])])
    df = _postings([("DBA", "postgresql expert")])
    out = tag(df, skills)
    assert out.loc[0, "skills"] == []


def test_case_insensitive_match() -> None:
    skills = _skills([("Tableau", [])])
    df = _postings([("BI dev", "tableau dashboards required")])
    out = tag(df, skills)
    assert out.loc[0, "skills"] == ["Tableau"]


def test_empty_input_returns_empty_list_not_none() -> None:
    skills = _skills([("SQL", [])])
    df = _postings([("Designer", "No tech here")])
    out = tag(df, skills)
    assert out.loc[0, "skills"] == []


def test_dedupes_preferred_label_when_pref_and_alt_both_hit() -> None:
    skills = _skills([("Python (computer programming)", ["Python"])])
    df = _postings([("Engineer", "We use Python and python3")])
    out = tag(df, skills)
    assert out.loc[0, "skills"] == ["Python (computer programming)"]


def test_sorted_output_for_determinism() -> None:
    skills = _skills([("SQL", []), ("Python (computer programming)", []), ("Tableau", [])])
    df = _postings([("Data Analyst", "SQL + Tableau + Python (computer programming) required")])
    out = tag(df, skills)
    assert out.loc[0, "skills"] == sorted(out.loc[0, "skills"])


def test_handles_null_description() -> None:
    skills = _skills([("SQL", [])])
    df = pd.DataFrame([{"title": "SQL Engineer", "description": None}])
    out = tag(df, skills)
    assert out.loc[0, "skills"] == ["SQL"]


def test_empty_postings_frame() -> None:
    skills = _skills([("SQL", [])])
    df = _postings([])
    out = tag(df, skills)
    assert "skills" in out.columns
    assert len(out) == 0


def test_focus_isco_filters_off_domain_skills() -> None:
    """Skills not linked to any focus ISCO code are dropped before matching."""
    skills = _skills(
        [
            ("SQL", []),
            ("packaging engineering", []),
            ("journalism", []),
        ],
        iscos=[["2511", "2521"], ["7549"], ["2642"]],
    )
    df = _postings([("Data Analyst", "SQL + packaging engineering + journalism mentioned")])
    out = tag(df, skills, focus_isco=["2511", "2521"])
    assert out.loc[0, "skills"] == ["SQL"]


def test_focus_isco_drops_unmapped_skills() -> None:
    """Skills with empty related_isco_codes are dropped when focus is set."""
    skills = _skills(
        [("SQL", []), ("unmapped skill", [])],
        iscos=[["2511"], []],
    )
    df = _postings([("Analyst", "SQL and unmapped skill")])
    out = tag(df, skills, focus_isco=["2511"])
    assert out.loc[0, "skills"] == ["SQL"]


def test_focus_isco_none_preserves_legacy_behaviour() -> None:
    """No focus_isco passed = full dictionary scan (PR 2b baseline)."""
    skills = _skills(
        [("SQL", []), ("packaging engineering", [])],
        iscos=[["2511"], ["7549"]],
    )
    df = _postings([("DA", "SQL + packaging engineering")])
    out = tag(df, skills, focus_isco=None)
    assert out.loc[0, "skills"] == ["SQL", "packaging engineering"]
