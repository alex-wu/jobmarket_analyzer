from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from jobpipe import benchmarks
from jobpipe.benchmarks import oecd
from jobpipe.benchmarks.oecd import OecdBenchmark, OecdConfig, _parse_dataset
from jobpipe.schemas import BenchmarkSchema

FIXTURE = Path(__file__).parent.parent / "fixtures" / "benchmarks" / "oecd" / "sample.json"
RATES = {"EUR": 1.0, "GBP": 0.85}


@pytest.fixture
def payload() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_parse_extracts_eur_observation(payload: dict) -> None:
    df = _parse_dataset(
        payload,
        isco_codes=["2511"],
        countries=["IE"],
        retrieved_at=datetime(2026, 5, 14, tzinfo=UTC),
        source_url="http://example.test/oecd",
        rates=RATES,
    )
    assert len(df) == 1
    row = df.iloc[0]
    assert row["isco_code"] == "2511"
    assert row["country"] == "IE"
    assert row["currency"] == "EUR"
    assert row["median_eur"] == pytest.approx(55000.0)
    assert row["source"] == "oecd"
    assert row["period"] == "2022"


def test_parse_converts_gbp_to_eur(payload: dict) -> None:
    # 2511 in GB has UNIT_MEASURE=GBP, value 62000 -> 62000 / 0.85 EUR
    df = _parse_dataset(
        payload,
        isco_codes=["2511"],
        countries=["GB"],
        retrieved_at=datetime(2026, 5, 14, tzinfo=UTC),
        source_url="http://example.test/oecd",
        rates=RATES,
    )
    assert len(df) == 1
    assert df.iloc[0]["currency"] == "EUR"
    assert df.iloc[0]["median_eur"] == pytest.approx(62000.0 / 0.85)


def test_parse_drops_row_with_unknown_currency(payload: dict) -> None:
    # If ECB rates don't list the row's currency, convert_benchmark_to_eur drops it.
    # GB row in the fixture has currency=GBP; with no GBP rate it gets dropped.
    rates_eur_only = {"EUR": 1.0}
    df = _parse_dataset(
        payload,
        isco_codes=["2511"],
        countries=["IE", "GB"],
        retrieved_at=datetime(2026, 5, 14, tzinfo=UTC),
        source_url="http://example.test/oecd",
        rates=rates_eur_only,
    )
    assert set(df["country"]) == {"IE"}


def test_parse_country_filter_excludes_others(payload: dict) -> None:
    df = _parse_dataset(
        payload,
        isco_codes=["2511", "2521"],
        countries=["IE"],
        retrieved_at=datetime(2026, 5, 14, tzinfo=UTC),
        source_url="http://example.test/oecd",
        rates=RATES,
    )
    assert (df["country"] == "IE").all()
    assert set(df["isco_code"]) == {"2511", "2521"}


def test_parse_isco_filter_excludes_others(payload: dict) -> None:
    df = _parse_dataset(
        payload,
        isco_codes=["2511"],
        countries=["IE", "GB"],
        retrieved_at=datetime(2026, 5, 14, tzinfo=UTC),
        source_url="http://example.test/oecd",
        rates=RATES,
    )
    assert (df["isco_code"] == "2511").all()


def test_parse_validates_under_strict_schema(payload: dict) -> None:
    df = _parse_dataset(
        payload,
        isco_codes=["2511"],
        countries=["IE"],
        retrieved_at=datetime(2026, 5, 14, tzinfo=UTC),
        source_url="http://example.test/oecd",
        rates=RATES,
    )
    BenchmarkSchema.validate(df, lazy=True)


def test_parse_empty_payload_returns_empty() -> None:
    df = _parse_dataset(
        {},
        isco_codes=["2511"],
        countries=["IE"],
        retrieved_at=datetime(2026, 5, 14, tzinfo=UTC),
        source_url="http://example.test/oecd",
        rates=RATES,
    )
    assert df.empty


def test_parse_missing_isco_dim_returns_empty() -> None:
    bad = {
        "data": {
            "dataSets": [{"observations": {"0": [1.0]}}],
            "structures": [
                {"dimensions": {"observation": [{"id": "SOMETHING_ELSE", "values": [{"id": "x"}]}]}}
            ],
        }
    }
    df = _parse_dataset(
        bad,
        isco_codes=["2511"],
        countries=["IE"],
        retrieved_at=datetime(2026, 5, 14, tzinfo=UTC),
        source_url="http://example.test/oecd",
        rates=RATES,
    )
    assert df.empty


def test_fetch_returns_empty_on_cloudflare_html(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/html; charset=UTF-8"},
            text="<html>Just a moment...</html>",
        )

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(oecd, "httpx", _wrap_httpx(httpx.Client(transport=transport)))

    adapter = OecdBenchmark()
    cfg = OecdConfig(isco_codes=["2511"], countries=["IE"])
    df = adapter.fetch(cfg, rates=RATES)
    assert df.empty


def test_fetch_returns_empty_on_403(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, headers={"content-type": "text/html"}, text="forbidden")

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(oecd, "httpx", _wrap_httpx(httpx.Client(transport=transport)))

    adapter = OecdBenchmark()
    cfg = OecdConfig(isco_codes=["2511"], countries=["IE"])
    df = adapter.fetch(cfg, rates=RATES)
    assert df.empty


def test_fetch_happy_path(payload: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            json=payload,
        )

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(oecd, "httpx", _wrap_httpx(httpx.Client(transport=transport)))

    adapter = OecdBenchmark()
    cfg = OecdConfig(isco_codes=["2511"], countries=["IE"])
    df = adapter.fetch(cfg, rates=RATES)
    assert len(df) == 1
    assert df.iloc[0]["isco_code"] == "2511"


def test_self_registers_under_oecd_name() -> None:
    assert "oecd" in benchmarks.names()
    assert isinstance(benchmarks.get("oecd"), OecdBenchmark)


class _HttpxShim:
    def __init__(self, client: httpx.Client) -> None:
        self._client = client
        self.HTTPError = httpx.HTTPError
        self.Response = httpx.Response
        self.Request = httpx.Request
        self.ConnectError = httpx.ConnectError

    def get(self, url: str, **kwargs: object) -> httpx.Response:
        return self._client.get(url)


def _wrap_httpx(client: httpx.Client) -> _HttpxShim:
    return _HttpxShim(client)
