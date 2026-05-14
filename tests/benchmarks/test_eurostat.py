from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from jobpipe import benchmarks
from jobpipe.benchmarks import eurostat
from jobpipe.benchmarks.eurostat import (
    EurostatBenchmark,
    EurostatConfig,
    _parse_dataset,
)
from jobpipe.schemas import BenchmarkSchema

FIXTURE = Path(__file__).parent.parent / "fixtures" / "benchmarks" / "eurostat" / "sample.json"
RATES = {"EUR": 1.0}


@pytest.fixture
def payload() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_parse_strips_oc_prefix_and_keeps_4_digit(payload: dict) -> None:
    df = _parse_dataset(
        payload,
        isco_codes=["2511", "2521"],
        countries=["IE"],
        retrieved_at=datetime(2026, 5, 14, tzinfo=UTC),
        source_url="http://test.example/eurostat",
        rates=RATES,
    )
    assert set(df["isco_code"]) == {"2511", "2521"}
    # OC2 and OC25 must be dropped (not 4-digit after prefix strip).
    assert (df["isco_code"].str.len() == 4).all()


def test_parse_extracts_latest_vintage(payload: dict) -> None:
    df = _parse_dataset(
        payload,
        isco_codes=["2511"],
        countries=["IE"],
        retrieved_at=datetime(2026, 5, 14, tzinfo=UTC),
        source_url="http://test.example/eurostat",
        rates=RATES,
    )
    # 2022 is the latest vintage in the fixture.
    assert (df["period"] == "2022").all()
    # 2511 IE 2022 -> value 58000.
    assert df.iloc[0]["median_eur"] == pytest.approx(58000.0)


def test_parse_emits_row_per_isco_and_country(payload: dict) -> None:
    df = _parse_dataset(
        payload,
        isco_codes=["2511", "2521"],
        countries=["IE", "DE"],
        retrieved_at=datetime(2026, 5, 14, tzinfo=UTC),
        source_url="http://test.example/eurostat",
        rates=RATES,
    )
    pairs = set(zip(df["isco_code"], df["country"], strict=False))
    assert pairs == {("2511", "IE"), ("2511", "DE"), ("2521", "IE"), ("2521", "DE")}


def test_parse_country_filter(payload: dict) -> None:
    df = _parse_dataset(
        payload,
        isco_codes=["2511"],
        countries=["IE"],
        retrieved_at=datetime(2026, 5, 14, tzinfo=UTC),
        source_url="http://test.example/eurostat",
        rates=RATES,
    )
    assert (df["country"] == "IE").all()


def test_parse_isco_filter(payload: dict) -> None:
    df = _parse_dataset(
        payload,
        isco_codes=["2511"],
        countries=["IE", "DE"],
        retrieved_at=datetime(2026, 5, 14, tzinfo=UTC),
        source_url="http://test.example/eurostat",
        rates=RATES,
    )
    assert (df["isco_code"] == "2511").all()


def test_parse_validates_under_strict_schema(payload: dict) -> None:
    df = _parse_dataset(
        payload,
        isco_codes=["2511", "2521"],
        countries=["IE"],
        retrieved_at=datetime(2026, 5, 14, tzinfo=UTC),
        source_url="http://test.example/eurostat",
        rates=RATES,
    )
    BenchmarkSchema.validate(df, lazy=True)


def test_parse_empty_payload_returns_empty() -> None:
    df = _parse_dataset(
        {},
        isco_codes=["2511"],
        countries=["IE"],
        retrieved_at=datetime(2026, 5, 14, tzinfo=UTC),
        source_url="http://test.example/eurostat",
        rates=RATES,
    )
    assert df.empty


def test_parse_returns_empty_when_no_requested_codes_present(payload: dict) -> None:
    df = _parse_dataset(
        payload,
        isco_codes=["9999"],  # not in fixture
        countries=["IE"],
        retrieved_at=datetime(2026, 5, 14, tzinfo=UTC),
        source_url="http://test.example/eurostat",
        rates=RATES,
    )
    assert df.empty


def test_parse_missing_dimensions_returns_empty() -> None:
    bad = {"id": ["foo"], "size": [1], "dimension": {}, "value": [1.0]}
    df = _parse_dataset(
        bad,
        isco_codes=["2511"],
        countries=["IE"],
        retrieved_at=datetime(2026, 5, 14, tzinfo=UTC),
        source_url="http://test.example/eurostat",
        rates=RATES,
    )
    assert df.empty


def test_fetch_happy_path(payload: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(eurostat, "httpx", _wrap_httpx(httpx.Client(transport=transport)))

    adapter = EurostatBenchmark()
    cfg = EurostatConfig(isco_codes=["2511"], countries=["IE"])
    df = adapter.fetch(cfg, rates=RATES)
    assert len(df) == 1
    assert df.iloc[0]["isco_code"] == "2511"


def test_fetch_returns_empty_on_404(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="not found")

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(eurostat, "httpx", _wrap_httpx(httpx.Client(transport=transport)))

    adapter = EurostatBenchmark()
    cfg = EurostatConfig(isco_codes=["2511"], countries=["IE"])
    df = adapter.fetch(cfg, rates=RATES)
    assert df.empty


def test_self_registers_under_eurostat_name() -> None:
    assert "eurostat" in benchmarks.names()
    assert isinstance(benchmarks.get("eurostat"), EurostatBenchmark)


class _HttpxShim:
    def __init__(self, client: httpx.Client) -> None:
        self._client = client
        self.HTTPError = httpx.HTTPError
        self.Response = httpx.Response
        self.Request = httpx.Request
        self.ConnectError = httpx.ConnectError

    def get(self, url: str, **kwargs: object) -> httpx.Response:
        return self._client.get(url, params=kwargs.get("params"))


def _wrap_httpx(client: httpx.Client) -> _HttpxShim:
    return _HttpxShim(client)
