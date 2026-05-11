"""Greenhouse adapter tests — JSON fixtures + httpx.MockTransport (no live HTTP)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pandas as pd
import pytest

from jobpipe.schemas import PostingSchema
from jobpipe.sources import SourceFetchError
from jobpipe.sources.greenhouse import BASE_URL, GreenhouseAdapter, GreenhouseConfig

FIXTURES = Path(__file__).parent.parent / "fixtures" / "greenhouse"


def _load(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _mock(handler: httpx.MockTransport) -> httpx.Client:
    return httpx.Client(transport=handler, timeout=5.0)


def _companies(tmp_path: Path, slugs: list[str]) -> Path:
    body = "greenhouse:\n" + "".join(f"  - {s}\n" for s in slugs) if slugs else "greenhouse: []\n"
    p = tmp_path / "dublin_tech.yaml"
    p.write_text(body, encoding="utf-8")
    return p


def test_fetch_returns_normalised_dataframe(tmp_path: Path) -> None:
    cf = _companies(tmp_path, ["intercom"])

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_load("board_intercom.json"))

    cfg = GreenhouseConfig(
        companies_file=cf,
        keywords=["analyst", "analytics"],
        countries=["ie", "remote-europe"],
    )
    df = GreenhouseAdapter().fetch(cfg, client=_mock(httpx.MockTransport(handler)))

    assert isinstance(df, pd.DataFrame)
    # Fixture has 4 jobs: 1 Dublin analyst (kept), 1 SF EM (dropped: country + keyword), 1 Remote-EU analytics (kept), 1 Dublin CX (dropped: keyword).
    assert len(df) == 2
    PostingSchema.validate(df, lazy=True)
    assert set(df["title"]) == {"Senior Data Analyst", "Analytics Engineer"}


def test_fetch_required_fields_present(tmp_path: Path) -> None:
    cf = _companies(tmp_path, ["intercom"])

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_load("board_intercom.json"))

    cfg = GreenhouseConfig(
        companies_file=cf,
        keywords=["analyst"],
        countries=["ie"],
    )
    df = GreenhouseAdapter().fetch(cfg, client=_mock(httpx.MockTransport(handler)))
    row = df.iloc[0]
    assert row["source"] == "greenhouse"
    assert row["posting_id"]
    assert row["posting_url"].startswith("http")
    assert row["country"] == "IE"
    assert row["company"] == "intercom"
    assert row["title"] == "Senior Data Analyst"


def test_fetch_filters_out_unwanted_countries(tmp_path: Path) -> None:
    cf = _companies(tmp_path, ["intercom"])

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_load("board_intercom.json"))

    cfg = GreenhouseConfig(
        companies_file=cf,
        keywords=[],  # no keyword filter — country filter only
        countries=["ie"],  # remote-europe excluded
    )
    df = GreenhouseAdapter().fetch(cfg, client=_mock(httpx.MockTransport(handler)))
    # Only the two Dublin rows survive (no remote-EU since we didn't allow it).
    assert len(df) == 2
    assert (df["country"] == "IE").all()


def test_fetch_marks_remote_rows(tmp_path: Path) -> None:
    cf = _companies(tmp_path, ["intercom"])

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_load("board_intercom.json"))

    cfg = GreenhouseConfig(
        companies_file=cf,
        keywords=["analytics"],
        countries=["ie", "remote-europe"],
    )
    df = GreenhouseAdapter().fetch(cfg, client=_mock(httpx.MockTransport(handler)))
    row = df[df["title"] == "Analytics Engineer"].iloc[0]
    assert bool(row["remote"]) is True
    assert row["country"] == "IE"  # anchored to first real ISO-2 in allowed list


def test_fetch_skips_slug_on_404_and_continues(tmp_path: Path) -> None:
    cf = _companies(tmp_path, ["badslug", "intercom"])
    calls: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        slug = req.url.path.rsplit("/", 2)[-2]
        calls.append(slug)
        if slug == "badslug":
            return httpx.Response(404)
        return httpx.Response(200, json=_load("board_intercom.json"))

    cfg = GreenhouseConfig(
        companies_file=cf,
        keywords=["analyst", "analytics"],
        countries=["ie", "remote-europe"],
    )
    df = GreenhouseAdapter().fetch(cfg, client=_mock(httpx.MockTransport(handler)))
    assert calls == ["badslug", "intercom"]
    assert len(df) == 2


def test_fetch_raises_on_persistent_5xx(tmp_path: Path) -> None:
    cf = _companies(tmp_path, ["intercom"])

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    cfg = GreenhouseConfig(companies_file=cf, keywords=["analyst"], countries=["ie"])
    with pytest.raises(SourceFetchError, match="greenhouse"):
        GreenhouseAdapter().fetch(cfg, client=_mock(httpx.MockTransport(handler)))


def test_fetch_returns_empty_for_empty_board(tmp_path: Path) -> None:
    cf = _companies(tmp_path, ["intercom"])

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_load("board_empty.json"))

    cfg = GreenhouseConfig(companies_file=cf, keywords=["analyst"], countries=["ie"])
    df = GreenhouseAdapter().fetch(cfg, client=_mock(httpx.MockTransport(handler)))
    assert df.empty


def test_fetch_returns_empty_when_no_slugs(tmp_path: Path) -> None:
    cf = _companies(tmp_path, [])
    cfg = GreenhouseConfig(companies_file=cf, keywords=["analyst"], countries=["ie"])
    # No client needed because we should bail before any HTTP call.
    df = GreenhouseAdapter().fetch(cfg)
    assert df.empty


def test_fetch_caps_at_max_results(tmp_path: Path) -> None:
    cf = _companies(tmp_path, ["intercom", "stripe"])

    def handler(req: httpx.Request) -> httpx.Response:
        slug = req.url.path.rsplit("/", 2)[-2]
        fname = "board_intercom.json" if slug == "intercom" else "board_stripe.json"
        return httpx.Response(200, json=_load(fname))

    cfg = GreenhouseConfig(
        companies_file=cf,
        keywords=["analyst", "analytics"],
        countries=["ie", "remote-europe"],
        max_results=1,
    )
    df = GreenhouseAdapter().fetch(cfg, client=_mock(httpx.MockTransport(handler)))
    assert len(df) == 1


def test_fetch_hits_documented_endpoint_shape(tmp_path: Path) -> None:
    cf = _companies(tmp_path, ["intercom"])
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(200, json=_load("board_empty.json"))

    cfg = GreenhouseConfig(companies_file=cf, keywords=["analyst"], countries=["ie"])
    GreenhouseAdapter().fetch(cfg, client=_mock(httpx.MockTransport(handler)))
    assert seen[0].url.host == httpx.URL(BASE_URL).host
    assert seen[0].url.path == "/v1/boards/intercom/jobs"
    assert seen[0].url.params["content"] == "true"


def test_fetch_drops_rows_with_missing_id_or_malformed_url(tmp_path: Path) -> None:
    cf = _companies(tmp_path, ["edge"])

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_load("board_edge_cases.json"))

    cfg = GreenhouseConfig(
        companies_file=cf,
        keywords=[],  # no keyword filter — exercise defensive guards directly
        countries=["ie"],
    )
    df = GreenhouseAdapter().fetch(cfg, client=_mock(httpx.MockTransport(handler)))
    # Of the 3 fixture rows: id=null is dropped, absolute_url="not-a-url" is dropped,
    # leaving the offices-fallback row.
    assert len(df) == 1
    assert df.iloc[0]["title"] == "Analytics Lead From Offices Fallback"
    assert df.iloc[0]["location_raw"] == "Ireland"


def test_adapter_self_registered_on_import() -> None:
    import jobpipe.sources.greenhouse  # noqa: F401
    from jobpipe import sources

    assert "greenhouse" in sources.names()
    assert sources.get("greenhouse").name == "greenhouse"
