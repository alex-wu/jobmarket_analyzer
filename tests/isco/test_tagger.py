from __future__ import annotations

import pandas as pd
import pytest

from jobpipe.isco.tagger import _clean_title, tag


@pytest.fixture
def labels() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ("2511", "Systems analysts", "preferred"),
            ("2511", "data analyst", "alt"),
            ("2511", "data scientist", "alt"),
            ("2521", "Database designers and administrators", "preferred"),
            ("2521", "database administrator", "alt"),
            ("2421", "Management and organization analysts", "preferred"),
            ("2421", "business analyst", "alt"),
        ],
        columns=["isco_code", "label", "label_kind"],
    )


def _frame(titles: list[str | None]) -> pd.DataFrame:
    return pd.DataFrame({"title": titles, "posting_id": [f"p{i}" for i in range(len(titles))]})


def test_clean_strips_parentheticals_and_lowercases() -> None:
    assert _clean_title("Senior Data Analyst (Dublin)") == "senior data analyst"
    assert _clean_title("Analyst (m/f/d) - Berlin") == "analyst berlin"


def test_clean_handles_none_and_nan() -> None:
    assert _clean_title(None) == ""
    assert _clean_title(float("nan")) == ""
    assert _clean_title("") == ""


def test_exact_match_fires_fuzzy_method(labels: pd.DataFrame) -> None:
    df = tag(_frame(["data analyst"]), labels)
    assert df.loc[0, "isco_code"] == "2511"
    assert df.loc[0, "isco_match_method"] == "fuzzy"
    assert df.loc[0, "isco_match_score"] == 1.0


def test_match_above_cutoff_keeps_match(labels: pd.DataFrame) -> None:
    df = tag(_frame(["Senior Data Analyst (Dublin)"]), labels)
    assert df.loc[0, "isco_code"] == "2511"
    assert df.loc[0, "isco_match_method"] == "fuzzy"
    assert df.loc[0, "isco_match_score"] >= 0.88


def test_match_below_cutoff_returns_none(labels: pd.DataFrame) -> None:
    df = tag(_frame(["Lead Underwater Welder"]), labels)
    assert df.loc[0, "isco_code"] is None
    assert df.loc[0, "isco_match_method"] == "none"
    assert df.loc[0, "isco_match_score"] is None


def test_business_analyst_maps_to_2421(labels: pd.DataFrame) -> None:
    df = tag(_frame(["Business Analyst"]), labels)
    assert df.loc[0, "isco_code"] == "2421"


def test_dba_maps_to_2521(labels: pd.DataFrame) -> None:
    df = tag(_frame(["Database Administrator"]), labels)
    assert df.loc[0, "isco_code"] == "2521"


def test_empty_title_returns_none(labels: pd.DataFrame) -> None:
    df = tag(_frame(["", None]), labels)
    assert df.loc[0, "isco_match_method"] == "none"
    assert df.loc[1, "isco_match_method"] == "none"
    assert df.loc[0, "isco_code"] is None
    assert df.loc[1, "isco_code"] is None


def test_empty_labels_frame_returns_all_none(labels: pd.DataFrame) -> None:
    empty_labels = labels.iloc[0:0]
    df = tag(_frame(["data analyst"]), empty_labels)
    assert df.loc[0, "isco_match_method"] == "none"
    assert df.loc[0, "isco_code"] is None


def test_empty_postings_frame_passthrough(labels: pd.DataFrame) -> None:
    df = tag(_frame([]), labels)
    assert df.empty
    assert "isco_code" in df.columns
    assert "isco_match_method" in df.columns
    assert "isco_match_score" in df.columns


def test_score_cutoff_param_overrides_default(labels: pd.DataFrame) -> None:
    # "analyt" is too short to clear default 88, but lowering cutoff lets a sloppy match through.
    strict = tag(_frame(["analyt"]), labels, score_cutoff=95)
    assert strict.loc[0, "isco_code"] is None
    loose = tag(_frame(["analyt"]), labels, score_cutoff=50)
    assert loose.loc[0, "isco_code"] is not None
    assert loose.loc[0, "isco_match_method"] == "fuzzy"


def test_does_not_mutate_input(labels: pd.DataFrame) -> None:
    src = _frame(["data analyst"])
    src_copy = src.copy()
    _ = tag(src, labels)
    pd.testing.assert_frame_equal(src, src_copy)


def test_score_in_unit_interval(labels: pd.DataFrame) -> None:
    df = tag(_frame(["data analyst", "Senior Data Analyst (Dublin)"]), labels)
    scores = df["isco_match_score"].dropna().tolist()
    assert all(0.0 <= s <= 1.0 for s in scores)
