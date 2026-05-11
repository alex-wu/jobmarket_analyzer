"""ECB FX rate loader + pure converter tests."""

from __future__ import annotations

import io
import os
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pandas as pd
import pytest

from jobpipe import fx


def _zip_response(csv_text: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(fx.ECB_CSV_NAME, csv_text)
    return buf.getvalue()


@pytest.fixture
def fake_ecb_client() -> httpx.Client:
    csv_text = "Date, USD, GBP, AUD\n11 May 2026, 1.0850, 0.8500, 1.6500\n"
    body = _zip_response(csv_text)

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_load_rates_fetches_and_caches(tmp_path: Path, fake_ecb_client: httpx.Client) -> None:
    cache = tmp_path / "ecb.csv"
    rates = fx.load_rates(cache_path=cache, client=fake_ecb_client)
    assert rates["EUR"] == 1.0
    assert rates["GBP"] == pytest.approx(0.85)
    assert rates["USD"] == pytest.approx(1.085)
    assert cache.exists()


def test_load_rates_reuses_cache_when_fresh(tmp_path: Path) -> None:
    cache = tmp_path / "ecb.csv"
    cache.write_text("Date, GBP\n10 May 2026, 0.9000\n", encoding="utf-8")

    def boom(_: httpx.Request) -> httpx.Response:
        raise AssertionError("HTTP should not be called when cache is fresh")

    fresh_client = httpx.Client(transport=httpx.MockTransport(boom))
    rates = fx.load_rates(cache_path=cache, client=fresh_client)
    assert rates["GBP"] == pytest.approx(0.90)


def test_load_rates_refetches_when_cache_stale(
    tmp_path: Path, fake_ecb_client: httpx.Client
) -> None:
    cache = tmp_path / "ecb.csv"
    cache.write_text("Date, GBP\n01 Jan 2020, 0.7000\n", encoding="utf-8")
    stale = (datetime.now(UTC) - timedelta(days=10)).timestamp()
    os.utime(cache, (stale, stale))

    rates = fx.load_rates(cache_path=cache, client=fake_ecb_client)
    assert rates["GBP"] == pytest.approx(0.85)


def test_load_rates_rejects_malformed_csv(tmp_path: Path) -> None:
    cache = tmp_path / "ecb.csv"
    cache.write_text("only-a-header\n", encoding="utf-8")
    with pytest.raises(ValueError, match="malformed"):
        fx.load_rates(cache_path=cache)


def test_parse_csv_skips_na_and_unparseable_values() -> None:
    text = "Date, USD, XXX, BAD\n11 May 2026, 1.0850, N/A, notanumber\n"
    rates = fx._parse_csv(text)
    assert rates["USD"] == pytest.approx(1.085)
    assert "XXX" not in rates
    assert "BAD" not in rates


def test_convert_to_eur_applies_per_country_rates() -> None:
    df = pd.DataFrame(
        {
            "country": ["GB", "US", "FR"],
            "salary_min_eur": [50_000.0, 100_000.0, 60_000.0],
            "salary_max_eur": [60_000.0, 120_000.0, 70_000.0],
            "salary_annual_eur_p50": [55_000.0, 110_000.0, 65_000.0],
        }
    )
    rates = {"EUR": 1.0, "GBP": 0.85, "USD": 1.10}
    out = fx.convert_to_eur(df, rates)

    assert out.loc[0, "salary_min_eur"] == pytest.approx(50_000 / 0.85)
    assert out.loc[1, "salary_min_eur"] == pytest.approx(100_000 / 1.10)
    assert out.loc[2, "salary_min_eur"] == pytest.approx(60_000.0)


def test_convert_to_eur_nulls_when_currency_missing(caplog: pytest.LogCaptureFixture) -> None:
    df = pd.DataFrame(
        {
            "country": ["XX"],
            "salary_min_eur": [50_000.0],
            "salary_max_eur": [60_000.0],
            "salary_annual_eur_p50": [55_000.0],
        }
    )
    with caplog.at_level("WARNING", logger="jobpipe.fx"):
        out = fx.convert_to_eur(df, {"EUR": 1.0})
    assert pd.isna(out.loc[0, "salary_min_eur"])
    assert pd.isna(out.loc[0, "salary_max_eur"])
    assert any("no ECB rate" in r.message for r in caplog.records)


def test_convert_to_eur_empty_df_passes_through() -> None:
    df = pd.DataFrame(
        columns=["country", "salary_min_eur", "salary_max_eur", "salary_annual_eur_p50"]
    )
    out = fx.convert_to_eur(df, {"EUR": 1.0})
    assert out.empty


def test_convert_to_eur_does_not_warn_when_row_has_no_salary() -> None:
    df = pd.DataFrame(
        {
            "country": ["XX"],
            "salary_min_eur": [None],
            "salary_max_eur": [None],
            "salary_annual_eur_p50": [None],
        }
    )
    # Unknown country but null salary → silent, no warning.
    out = fx.convert_to_eur(df, {"EUR": 1.0})
    assert pd.isna(out.loc[0, "salary_min_eur"])
