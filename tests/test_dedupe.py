"""URL normalisation + posting hash + cross-source dedupe."""

from __future__ import annotations

import pandas as pd

from jobpipe import dedupe


def test_normalise_url_strips_utm_and_tracking_params() -> None:
    url = "https://Boards.greenhouse.io/Stripe/jobs/12345?utm_source=foo&gclid=xyz&keep=me"
    out = dedupe.normalise_url(url)
    assert "utm_" not in out
    assert "gclid" not in out
    assert "keep=me" in out
    assert "Boards" not in out  # host lowercased


def test_normalise_url_strips_trailing_slash_and_fragment() -> None:
    a = dedupe.normalise_url("https://example.com/job/1/?ref=x#section")
    b = dedupe.normalise_url("https://example.com/job/1?other=y")
    # `ref` stripped and `other` kept, plus trailing slash + fragment gone.
    # Both URLs reduce to the same scheme+host+path; differ only by remaining query.
    assert a.split("?")[0] == b.split("?")[0]
    assert "#" not in a
    assert a.endswith("/1")  # no trailing slash


def test_normalise_url_empty_input() -> None:
    assert dedupe.normalise_url("") == ""


def test_posting_hash_uses_url_when_present() -> None:
    row_a = pd.Series(
        {"posting_url": "https://ex.com/1?utm_x=1", "title": "X", "company": "C", "country": "GB"}
    )
    row_b = pd.Series(
        {
            "posting_url": "https://ex.com/1?utm_y=2",
            "title": "Different",
            "company": "Other",
            "country": "US",
        }
    )
    # Different tracking params, same canonical URL → same hash.
    assert dedupe.posting_hash(row_a) == dedupe.posting_hash(row_b)


def test_posting_hash_falls_back_to_tcc_when_url_absent() -> None:
    row_a = pd.Series(
        {"posting_url": "", "title": "Data Analyst", "company": "Acme", "country": "IE"}
    )
    row_b = pd.Series(
        {"posting_url": None, "title": "data analyst", "company": "ACME", "country": "ie"}
    )
    assert dedupe.posting_hash(row_a) == dedupe.posting_hash(row_b)


def test_posting_hash_url_and_fallback_yield_different_hashes() -> None:
    row_url = pd.Series(
        {"posting_url": "https://ex.com/1", "title": "T", "company": "C", "country": "GB"}
    )
    row_no_url = pd.Series({"posting_url": "", "title": "T", "company": "C", "country": "GB"})
    assert dedupe.posting_hash(row_url) != dedupe.posting_hash(row_no_url)


def test_cross_source_collapses_dupes_keeping_first() -> None:
    df = pd.DataFrame(
        [
            {
                "posting_url": "https://ex.com/a",
                "title": "T",
                "company": "C",
                "country": "GB",
                "source": "first",
            },
            {
                "posting_url": "https://ex.com/a?utm_x=1",
                "title": "T",
                "company": "C",
                "country": "GB",
                "source": "second",
            },
            {
                "posting_url": "https://ex.com/b",
                "title": "T",
                "company": "C",
                "country": "GB",
                "source": "third",
            },
        ]
    )
    out = dedupe.cross_source(df)
    assert len(out) == 2
    assert out.iloc[0]["source"] == "first"
    assert out.iloc[1]["source"] == "third"


def test_cross_source_empty_df() -> None:
    df = pd.DataFrame(columns=["posting_url", "title", "company", "country"])
    out = dedupe.cross_source(df)
    assert out.empty


def test_cross_source_is_idempotent() -> None:
    df = pd.DataFrame(
        [
            {"posting_url": "https://ex.com/a", "title": "T", "company": "C", "country": "GB"},
            {"posting_url": "https://ex.com/b", "title": "T", "company": "C", "country": "GB"},
        ]
    )
    once = dedupe.cross_source(df)
    twice = dedupe.cross_source(once)
    assert once.equals(twice)
