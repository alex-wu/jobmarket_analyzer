from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from jobpipe import benchmarks
from jobpipe.benchmarks import cso
from jobpipe.benchmarks.cso import (
    CsoBenchmark,
    CsoConfig,
    _isco_to_cso_bucket,
    _parse_dataset,
)
from jobpipe.schemas import BenchmarkSchema

FIXTURE = Path(__file__).parent.parent / "fixtures" / "benchmarks" / "cso" / "sample.json"


@pytest.fixture
def payload() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_bucket_map_professionals() -> None:
    assert _isco_to_cso_bucket("2511") == "1"
    assert _isco_to_cso_bucket("2521") == "1"
    assert _isco_to_cso_bucket("2423") == "1"
    assert _isco_to_cso_bucket("1234") == "1"
    assert _isco_to_cso_bucket("3434") == "1"


def test_bucket_map_clerical() -> None:
    assert _isco_to_cso_bucket("4110") == "2"
    assert _isco_to_cso_bucket("5223") == "2"


def test_bucket_map_manual() -> None:
    assert _isco_to_cso_bucket("6111") == "3"
    assert _isco_to_cso_bucket("9412") == "3"


def test_bucket_map_rejects_garbage() -> None:
    assert _isco_to_cso_bucket("") is None
    assert _isco_to_cso_bucket("abcd") is None


def test_parse_extracts_managers_bucket_for_2511(payload: dict) -> None:
    cfg = CsoConfig(isco_codes=["2511"], countries=["IE"])
    df = _parse_dataset(
        payload,
        cfg,
        isco_codes=cfg.isco_codes,
        countries=cfg.countries,
        retrieved_at=datetime(2026, 5, 14, tzinfo=UTC),
        source_url="http://test.example/cso",
    )
    assert len(df) == 1
    row = df.iloc[0]
    assert row["isco_code"] == "2511"
    assert row["country"] == "IE"
    assert row["period"] == "20254"  # latest in fixture
    assert row["currency"] == "EUR"
    # latest period (TLIST=20254 -> time_idx=1), All NACE (sector_idx=0), bucket "1" (emp_idx=1)
    # -> coords [STATISTIC=EHQ03C02(1), TLIST=1, NACE=0, EMP=1]
    # strides for size [2,2,2,4] row-major: [16, 8, 4, 1]
    # flat = 1*16 + 1*8 + 0*4 + 1*1 = 25 -> value[25] = 1200 -> x52 = 62 400
    assert row["median_eur"] == pytest.approx(1200 * 52)


def test_parse_emits_row_per_isco_code(payload: dict) -> None:
    cfg = CsoConfig(isco_codes=["2511", "4110"], countries=["IE"])
    df = _parse_dataset(
        payload,
        cfg,
        isco_codes=cfg.isco_codes,
        countries=cfg.countries,
        retrieved_at=datetime(2026, 5, 14, tzinfo=UTC),
        source_url="http://test.example/cso",
    )
    assert len(df) == 2
    assert set(df["isco_code"]) == {"2511", "4110"}


def test_parse_drops_non_ie_country(payload: dict) -> None:
    cfg = CsoConfig(isco_codes=["2511"], countries=["IE", "DE"])
    df = _parse_dataset(
        payload,
        cfg,
        isco_codes=cfg.isco_codes,
        countries=cfg.countries,
        retrieved_at=datetime(2026, 5, 14, tzinfo=UTC),
        source_url="http://test.example/cso",
    )
    assert set(df["country"]) == {"IE"}


def test_parse_empty_payload_returns_empty() -> None:
    cfg = CsoConfig(isco_codes=["2511"], countries=["IE"])
    df = _parse_dataset(
        {},
        cfg,
        isco_codes=cfg.isco_codes,
        countries=cfg.countries,
        retrieved_at=datetime(2026, 5, 14, tzinfo=UTC),
        source_url="http://test.example/cso",
    )
    assert df.empty


def test_parse_unknown_statistic_returns_empty(payload: dict) -> None:
    cfg = CsoConfig(isco_codes=["2511"], countries=["IE"], statistic="EHQ03_BOGUS")
    df = _parse_dataset(
        payload,
        cfg,
        isco_codes=cfg.isco_codes,
        countries=cfg.countries,
        retrieved_at=datetime(2026, 5, 14, tzinfo=UTC),
        source_url="http://test.example/cso",
    )
    assert df.empty


def test_parse_output_validates_under_strict_schema(payload: dict) -> None:
    cfg = CsoConfig(isco_codes=["2511", "2521", "2423"], countries=["IE"])
    df = _parse_dataset(
        payload,
        cfg,
        isco_codes=cfg.isco_codes,
        countries=cfg.countries,
        retrieved_at=datetime(2026, 5, 14, tzinfo=UTC),
        source_url="http://test.example/cso",
    )
    # BenchmarkSchema strict flips in the runner-fan-out commit; for now
    # validate columns are present and types match.
    BenchmarkSchema.validate(df, lazy=True)


def test_fetch_uses_mock_transport(payload: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    transport = httpx.MockTransport(handler)
    real_client = httpx.Client(transport=transport)
    monkeypatch.setattr(cso, "httpx", _wrap_httpx(real_client))

    adapter = CsoBenchmark()
    cfg = CsoConfig(isco_codes=["2511"], countries=["IE"])
    df = adapter.fetch(cfg)
    assert len(df) == 1
    assert df.iloc[0]["isco_code"] == "2511"


def test_fetch_returns_empty_on_404(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="Not Found")

    transport = httpx.MockTransport(handler)
    real_client = httpx.Client(transport=transport)
    monkeypatch.setattr(cso, "httpx", _wrap_httpx(real_client))

    adapter = CsoBenchmark()
    cfg = CsoConfig(isco_codes=["2511"], countries=["IE"])
    df = adapter.fetch(cfg)
    assert df.empty


def test_fetch_returns_empty_on_network_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("simulated network failure")

    transport = httpx.MockTransport(handler)
    real_client = httpx.Client(transport=transport)
    monkeypatch.setattr(cso, "httpx", _wrap_httpx(real_client))

    adapter = CsoBenchmark()
    cfg = CsoConfig(isco_codes=["2511"], countries=["IE"])
    df = adapter.fetch(cfg)
    assert df.empty


def test_self_registers_under_cso_name() -> None:
    assert "cso" in benchmarks.names()
    assert isinstance(benchmarks.get("cso"), CsoBenchmark)


# Helper -----------------------------------------------------------------


class _HttpxShim:
    """Stand-in for the ``httpx`` module that routes get() through a MockTransport."""

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
