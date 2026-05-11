"""Lever adapter tests — JSON fixtures + httpx.MockTransport (no live HTTP)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from jobpipe.schemas import PostingSchema
from jobpipe.sources import SourceFetchError
from jobpipe.sources.lever import BASE_URL, LeverAdapter, LeverConfig

FIXTURES = Path(__file__).parent.parent / "fixtures" / "lever"


def _load(name: str) -> list[dict[str, Any]] | dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _mock(handler: httpx.MockTransport) -> httpx.Client:
    return httpx.Client(transport=handler, timeout=5.0)


def _companies(tmp_path: Path, slugs: list[str]) -> Path:
    body = "lever:\n" + "".join(f"  - {s}\n" for s in slugs) if slugs else "lever: []\n"
    p = tmp_path / "dublin_tech.yaml"
    p.write_text(body, encoding="utf-8")
    return p


def test_fetch_returns_normalised_dataframe(tmp_path: Path) -> None:
    cf = _companies(tmp_path, ["palantir"])

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_load("postings_palantir.json"))

    cfg = LeverConfig(
        companies_file=cf,
        keywords=["analyst", "analytics"],
        countries=["ie", "remote-europe"],
    )
    df = LeverAdapter().fetch(cfg, client=_mock(httpx.MockTransport(handler)))
    # 4 fixture postings: Dublin analyst (kept), NY FDE (dropped country+kw), Remote-EU analytics
    # (kept), Dublin marketing (dropped keyword).
    assert len(df) == 2
    PostingSchema.validate(df, lazy=True)
    assert set(df["title"]) == {"Senior Data Analyst", "Analytics Engineer"}


def test_fetch_required_fields_present(tmp_path: Path) -> None:
    cf = _companies(tmp_path, ["palantir"])

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_load("postings_palantir.json"))

    cfg = LeverConfig(companies_file=cf, keywords=["analyst"], countries=["ie"])
    df = LeverAdapter().fetch(cfg, client=_mock(httpx.MockTransport(handler)))
    row = df.iloc[0]
    assert row["source"] == "lever"
    assert row["posting_id"]
    assert row["posting_url"].startswith("http")
    assert row["country"] == "IE"
    assert row["company"] == "palantir"


def test_fetch_filters_by_country(tmp_path: Path) -> None:
    cf = _companies(tmp_path, ["palantir"])

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_load("postings_palantir.json"))

    cfg = LeverConfig(companies_file=cf, keywords=[], countries=["ie"])
    df = LeverAdapter().fetch(cfg, client=_mock(httpx.MockTransport(handler)))
    # Only Dublin rows survive (no remote-europe in countries).
    assert len(df) == 2
    assert (df["country"] == "IE").all()


def test_fetch_marks_remote_rows(tmp_path: Path) -> None:
    cf = _companies(tmp_path, ["palantir"])

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_load("postings_palantir.json"))

    cfg = LeverConfig(
        companies_file=cf,
        keywords=["analytics"],
        countries=["ie", "remote-europe"],
    )
    df = LeverAdapter().fetch(cfg, client=_mock(httpx.MockTransport(handler)))
    row = df[df["title"] == "Analytics Engineer"].iloc[0]
    assert bool(row["remote"]) is True


def test_fetch_skips_slug_on_404_and_continues(tmp_path: Path) -> None:
    cf = _companies(tmp_path, ["dead", "palantir"])
    calls: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        slug = req.url.path.rsplit("/", 1)[-1]
        calls.append(slug)
        if slug == "dead":
            return httpx.Response(404)
        return httpx.Response(200, json=_load("postings_palantir.json"))

    cfg = LeverConfig(
        companies_file=cf,
        keywords=["analyst", "analytics"],
        countries=["ie", "remote-europe"],
    )
    df = LeverAdapter().fetch(cfg, client=_mock(httpx.MockTransport(handler)))
    assert calls == ["dead", "palantir"]
    assert len(df) == 2


def test_fetch_raises_on_persistent_5xx(tmp_path: Path) -> None:
    cf = _companies(tmp_path, ["palantir"])

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(502)

    cfg = LeverConfig(companies_file=cf, keywords=["analyst"], countries=["ie"])
    with pytest.raises(SourceFetchError, match="lever"):
        LeverAdapter().fetch(cfg, client=_mock(httpx.MockTransport(handler)))


def test_fetch_returns_empty_for_empty_postings(tmp_path: Path) -> None:
    cf = _companies(tmp_path, ["palantir"])

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_load("postings_empty.json"))

    cfg = LeverConfig(companies_file=cf, keywords=["analyst"], countries=["ie"])
    df = LeverAdapter().fetch(cfg, client=_mock(httpx.MockTransport(handler)))
    assert df.empty


def test_fetch_returns_empty_when_no_slugs(tmp_path: Path) -> None:
    cf = _companies(tmp_path, [])
    cfg = LeverConfig(companies_file=cf, keywords=["analyst"], countries=["ie"])
    df = LeverAdapter().fetch(cfg)
    assert df.empty


def test_fetch_ignores_non_list_response_body(tmp_path: Path) -> None:
    cf = _companies(tmp_path, ["palantir"])

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"error": "unexpected envelope"})

    cfg = LeverConfig(companies_file=cf, keywords=["analyst"], countries=["ie"])
    df = LeverAdapter().fetch(cfg, client=_mock(httpx.MockTransport(handler)))
    assert df.empty


def test_fetch_caps_at_max_results(tmp_path: Path) -> None:
    cf = _companies(tmp_path, ["palantir"])

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_load("postings_palantir.json"))

    cfg = LeverConfig(
        companies_file=cf,
        keywords=["analyst", "analytics"],
        countries=["ie", "remote-europe"],
        max_results=1,
    )
    df = LeverAdapter().fetch(cfg, client=_mock(httpx.MockTransport(handler)))
    assert len(df) == 1


def test_fetch_drops_rows_with_missing_id_or_malformed_url(tmp_path: Path) -> None:
    cf = _companies(tmp_path, ["x"])

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_load("postings_edge_cases.json"))

    cfg = LeverConfig(companies_file=cf, keywords=[], countries=["ie"])
    df = LeverAdapter().fetch(cfg, client=_mock(httpx.MockTransport(handler)))
    # 3 fixture rows: missing-id dropped, bad-url dropped, ISO-date row survives.
    assert len(df) == 1
    assert df.iloc[0]["title"] == "Analytics Lead With Iso Date"


def test_fetch_hits_documented_endpoint_shape(tmp_path: Path) -> None:
    cf = _companies(tmp_path, ["palantir"])
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(200, json=_load("postings_empty.json"))

    cfg = LeverConfig(companies_file=cf, keywords=["analyst"], countries=["ie"])
    LeverAdapter().fetch(cfg, client=_mock(httpx.MockTransport(handler)))
    assert seen[0].url.host == httpx.URL(BASE_URL).host
    assert seen[0].url.path == "/v0/postings/palantir"
    assert seen[0].url.params["mode"] == "json"


def test_adapter_self_registered_on_import() -> None:
    import jobpipe.sources.lever  # noqa: F401
    from jobpipe import sources

    assert "lever" in sources.names()
    assert sources.get("lever").name == "lever"
