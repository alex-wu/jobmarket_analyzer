"""Ashby adapter tests — JSON fixtures + httpx.MockTransport (no live HTTP)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from jobpipe.schemas import PostingSchema
from jobpipe.sources import SourceFetchError
from jobpipe.sources.ashby import (
    ANNUALISE_FACTOR,
    BASE_URL,
    INTERVAL_PERIOD_MAP,
    AshbyAdapter,
    AshbyConfig,
    _extract_compensation,
)

FIXTURES = Path(__file__).parent.parent / "fixtures" / "ashby"


def _load(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _mock(handler: httpx.MockTransport) -> httpx.Client:
    return httpx.Client(transport=handler, timeout=5.0)


def _companies(tmp_path: Path, slugs: list[str]) -> Path:
    body = "ashby:\n" + "".join(f"  - {s}\n" for s in slugs) if slugs else "ashby: []\n"
    p = tmp_path / "dublin_tech.yaml"
    p.write_text(body, encoding="utf-8")
    return p


def test_fetch_returns_normalised_dataframe(tmp_path: Path) -> None:
    cf = _companies(tmp_path, ["notion"])

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_load("board_notion.json"))

    cfg = AshbyConfig(
        companies_file=cf,
        keywords=["analyst", "analytics"],
        countries=["ie", "remote-europe"],
    )
    df = AshbyAdapter().fetch(cfg, client=_mock(httpx.MockTransport(handler)))
    # 4 fixture jobs: Dublin Analyst EUR (kept), NY FDE (dropped country+kw), Remote-EU Analytics EUR (kept),
    # Dublin Risk Analyst USD (kept — country matches, USD comp dropped but row kept).
    assert len(df) == 3
    PostingSchema.validate(df, lazy=True)


def test_fetch_extracts_eur_compensation(tmp_path: Path) -> None:
    cf = _companies(tmp_path, ["notion"])

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_load("board_notion.json"))

    cfg = AshbyConfig(
        companies_file=cf,
        keywords=["data analyst"],
        countries=["ie"],
    )
    df = AshbyAdapter().fetch(cfg, client=_mock(httpx.MockTransport(handler)))
    # "Senior Data Analyst, EMEA" matches; comp is in EUR (IE default) → populated.
    eur_row = df[df["title"] == "Senior Data Analyst, EMEA"].iloc[0]
    assert eur_row["salary_min_eur"] == 85000.0
    assert eur_row["salary_max_eur"] == 110000.0
    assert eur_row["salary_period"] == "annual"
    assert eur_row["salary_imputed"] is False


def test_fetch_drops_mismatched_currency_compensation(tmp_path: Path) -> None:
    cf = _companies(tmp_path, ["notion"])

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_load("board_notion.json"))

    cfg = AshbyConfig(
        companies_file=cf,
        keywords=["data analyst"],
        countries=["ie"],
    )
    df = AshbyAdapter().fetch(cfg, client=_mock(httpx.MockTransport(handler)))
    # "Data Analyst, Risk" is Dublin (IE) paid in USD → salary fields left null.
    usd_row = df[df["title"] == "Data Analyst, Risk"].iloc[0]
    import math

    assert math.isnan(usd_row["salary_min_eur"])
    assert math.isnan(usd_row["salary_max_eur"])
    assert usd_row["salary_period"] is None or pd_isna(usd_row["salary_period"])


def pd_isna(v: Any) -> bool:
    import pandas as pd

    return bool(pd.isna(v))


def test_fetch_annualises_hourly_comp(tmp_path: Path) -> None:
    cf = _companies(tmp_path, ["notion"])

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_load("board_notion.json"))

    cfg = AshbyConfig(
        companies_file=cf,
        keywords=["analytics"],
        countries=["ie", "remote-europe"],
    )
    df = AshbyAdapter().fetch(cfg, client=_mock(httpx.MockTransport(handler)))
    row = df[df["title"] == "Analytics Engineer"].iloc[0]
    # 40 EUR/hour * 2080 = 83,200; 55 EUR/hour * 2080 = 114,400.
    assert row["salary_min_eur"] == 83200.0
    assert row["salary_max_eur"] == 114400.0
    assert row["salary_period"] == "annual"


def test_fetch_marks_isremote_flag(tmp_path: Path) -> None:
    cf = _companies(tmp_path, ["notion"])

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_load("board_notion.json"))

    cfg = AshbyConfig(
        companies_file=cf,
        keywords=["analytics"],
        countries=["ie", "remote-europe"],
    )
    df = AshbyAdapter().fetch(cfg, client=_mock(httpx.MockTransport(handler)))
    row = df[df["title"] == "Analytics Engineer"].iloc[0]
    assert bool(row["remote"]) is True


def test_fetch_skips_slug_on_404_and_continues(tmp_path: Path) -> None:
    cf = _companies(tmp_path, ["dead", "notion"])
    calls: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        slug = req.url.path.rsplit("/", 1)[-1]
        calls.append(slug)
        if slug == "dead":
            return httpx.Response(404)
        return httpx.Response(200, json=_load("board_notion.json"))

    cfg = AshbyConfig(
        companies_file=cf,
        keywords=["data analyst", "analytics"],
        countries=["ie", "remote-europe"],
    )
    df = AshbyAdapter().fetch(cfg, client=_mock(httpx.MockTransport(handler)))
    assert calls == ["dead", "notion"]
    assert len(df) >= 2


def test_fetch_raises_on_persistent_5xx(tmp_path: Path) -> None:
    cf = _companies(tmp_path, ["notion"])

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    cfg = AshbyConfig(companies_file=cf, keywords=["analyst"], countries=["ie"])
    with pytest.raises(SourceFetchError, match="ashby"):
        AshbyAdapter().fetch(cfg, client=_mock(httpx.MockTransport(handler)))


def test_fetch_returns_empty_for_empty_board(tmp_path: Path) -> None:
    cf = _companies(tmp_path, ["notion"])

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_load("board_empty.json"))

    cfg = AshbyConfig(companies_file=cf, keywords=["analyst"], countries=["ie"])
    df = AshbyAdapter().fetch(cfg, client=_mock(httpx.MockTransport(handler)))
    assert df.empty


def test_fetch_returns_empty_when_no_slugs(tmp_path: Path) -> None:
    cf = _companies(tmp_path, [])
    cfg = AshbyConfig(companies_file=cf, keywords=["analyst"], countries=["ie"])
    df = AshbyAdapter().fetch(cfg)
    assert df.empty


def test_fetch_ignores_non_mapping_body(tmp_path: Path) -> None:
    cf = _companies(tmp_path, ["notion"])

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[1, 2, 3])

    cfg = AshbyConfig(companies_file=cf, keywords=["analyst"], countries=["ie"])
    df = AshbyAdapter().fetch(cfg, client=_mock(httpx.MockTransport(handler)))
    assert df.empty


def test_fetch_caps_at_max_results(tmp_path: Path) -> None:
    cf = _companies(tmp_path, ["notion"])

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_load("board_notion.json"))

    cfg = AshbyConfig(
        companies_file=cf,
        keywords=["analyst", "analytics"],
        countries=["ie", "remote-europe"],
        max_results=1,
    )
    df = AshbyAdapter().fetch(cfg, client=_mock(httpx.MockTransport(handler)))
    assert len(df) == 1


def test_fetch_hits_documented_endpoint_shape(tmp_path: Path) -> None:
    cf = _companies(tmp_path, ["notion"])
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(200, json=_load("board_empty.json"))

    cfg = AshbyConfig(companies_file=cf, keywords=["analyst"], countries=["ie"])
    AshbyAdapter().fetch(cfg, client=_mock(httpx.MockTransport(handler)))
    assert seen[0].url.host == httpx.URL(BASE_URL).host
    assert seen[0].url.path == "/posting-api/job-board/notion"
    assert seen[0].url.params["includeCompensation"] == "true"


def test_include_compensation_can_be_disabled(tmp_path: Path) -> None:
    cf = _companies(tmp_path, ["notion"])
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(200, json=_load("board_empty.json"))

    cfg = AshbyConfig(
        companies_file=cf,
        keywords=["analyst"],
        countries=["ie"],
        include_compensation=False,
    )
    AshbyAdapter().fetch(cfg, client=_mock(httpx.MockTransport(handler)))
    assert "includeCompensation" not in seen[0].url.params


def test_extract_compensation_returns_none_for_unknown_country() -> None:
    comp = {
        "compensationTiers": [
            {
                "components": [
                    {
                        "componentType": "Salary",
                        "interval": "1 YEAR",
                        "currencyCode": "EUR",
                        "minValue": 50000,
                        "maxValue": 70000,
                    }
                ]
            }
        ]
    }
    # Country code 'ZZ' isn't in COUNTRY_CURRENCY → return all-None.
    assert _extract_compensation(comp, "ZZ") == (None, None, None)


def test_extract_compensation_skips_non_salary_components() -> None:
    comp = {
        "compensationTiers": [
            {
                "components": [
                    {
                        "componentType": "Equity",
                        "interval": "1 YEAR",
                        "currencyCode": "EUR",
                        "minValue": 1000,
                        "maxValue": 2000,
                    }
                ]
            }
        ]
    }
    assert _extract_compensation(comp, "IE") == (None, None, None)


def test_extract_compensation_skips_invalid_numeric_values() -> None:
    comp = {
        "compensationTiers": [
            {
                "components": [
                    {
                        "componentType": "Salary",
                        "interval": "1 YEAR",
                        "currencyCode": "EUR",
                        "minValue": "not-a-number",
                        "maxValue": 70000,
                    }
                ]
            }
        ]
    }
    assert _extract_compensation(comp, "IE") == (None, None, None)


def test_extract_compensation_handles_unknown_interval() -> None:
    comp = {
        "compensationTiers": [
            {
                "components": [
                    {
                        "componentType": "Salary",
                        "interval": "per moon-cycle",
                        "currencyCode": "EUR",
                        "minValue": 1000,
                        "maxValue": 2000,
                    }
                ]
            }
        ]
    }
    assert _extract_compensation(comp, "IE") == (None, None, None)


def test_interval_period_map_covers_all_supported_periods() -> None:
    # Every annualisation period must be reachable through INTERVAL_PERIOD_MAP.
    reachable = set(INTERVAL_PERIOD_MAP.values())
    assert reachable == set(ANNUALISE_FACTOR.keys())


def test_adapter_self_registered_on_import() -> None:
    import jobpipe.sources.ashby  # noqa: F401
    from jobpipe import sources

    assert "ashby" in sources.names()
    assert sources.get("ashby").name == "ashby"
