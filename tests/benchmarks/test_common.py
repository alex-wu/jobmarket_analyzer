from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from jobpipe.benchmarks._common import (
    convert_benchmark_to_eur,
    last_fetch_mtime,
    should_skip,
)

# --- last_fetch_mtime ---


def test_last_fetch_mtime_returns_none_for_missing_dir(tmp_path: Path) -> None:
    assert last_fetch_mtime(tmp_path / "nope") is None


def test_last_fetch_mtime_returns_none_for_empty_dir(tmp_path: Path) -> None:
    d = tmp_path / "cso"
    d.mkdir()
    assert last_fetch_mtime(d) is None


def test_last_fetch_mtime_picks_newest_parquet(tmp_path: Path) -> None:
    d = tmp_path / "cso"
    d.mkdir()
    older = d / "older.parquet"
    newer = d / "newer.parquet"
    older.write_bytes(b"x")
    newer.write_bytes(b"x")
    import os
    import time

    base = time.time()
    os.utime(older, (base - 3600, base - 3600))
    os.utime(newer, (base, base))

    result = last_fetch_mtime(d)
    assert result is not None
    assert result.tzinfo is UTC
    assert (datetime.now(UTC) - result).total_seconds() < 60


def test_last_fetch_mtime_ignores_non_parquet(tmp_path: Path) -> None:
    d = tmp_path / "cso"
    d.mkdir()
    (d / "junk.txt").write_bytes(b"x")
    assert last_fetch_mtime(d) is None


# --- should_skip ---


def test_should_skip_false_when_no_prior_fetch() -> None:
    now = datetime(2026, 5, 14, 12, 0, tzinfo=UTC)
    assert should_skip(now, last_fetch=None, min_interval_hours=168) is False


def test_should_skip_true_inside_window() -> None:
    now = datetime(2026, 5, 14, 12, 0, tzinfo=UTC)
    last = now - timedelta(hours=3)
    assert should_skip(now, last_fetch=last, min_interval_hours=24) is True


def test_should_skip_false_at_window_boundary() -> None:
    now = datetime(2026, 5, 14, 12, 0, tzinfo=UTC)
    last = now - timedelta(hours=24)
    assert should_skip(now, last_fetch=last, min_interval_hours=24) is False


def test_should_skip_false_past_window() -> None:
    now = datetime(2026, 5, 14, 12, 0, tzinfo=UTC)
    last = now - timedelta(hours=200)
    assert should_skip(now, last_fetch=last, min_interval_hours=168) is False


def test_should_skip_false_when_interval_zero() -> None:
    now = datetime(2026, 5, 14, 12, 0, tzinfo=UTC)
    last = now - timedelta(minutes=1)
    assert should_skip(now, last_fetch=last, min_interval_hours=0) is False


# --- convert_benchmark_to_eur ---


def _bench(currency: str, median: float, p25: float | None = None) -> dict[str, object]:
    return {
        "isco_code": "2511",
        "country": "IE",
        "period": "2022",
        "currency": currency,
        "median_eur": median,
        "p25_eur": p25,
        "p75_eur": None,
        "n_observations": None,
        "source": "test",
        "source_url": "http://example.test",
        "retrieved_at": pd.Timestamp("2026-05-14", tz="UTC"),
    }


def test_convert_eur_passthrough_unchanged() -> None:
    df = pd.DataFrame([_bench("EUR", 50000.0, 40000.0)])
    rates = {"EUR": 1.0, "GBP": 0.85}
    out = convert_benchmark_to_eur(df, rates)
    assert out.loc[0, "median_eur"] == 50000.0
    assert out.loc[0, "p25_eur"] == 40000.0
    assert out.loc[0, "currency"] == "EUR"


def test_convert_gbp_divides_by_rate() -> None:
    df = pd.DataFrame([_bench("GBP", 42500.0)])
    rates = {"EUR": 1.0, "GBP": 0.85}
    out = convert_benchmark_to_eur(df, rates)
    assert out.loc[0, "median_eur"] == pytest.approx(50000.0)
    assert out.loc[0, "currency"] == "EUR"


def test_convert_drops_rows_with_unknown_currency() -> None:
    df = pd.DataFrame(
        [
            _bench("EUR", 50000.0),
            _bench("XYZ", 99999.0),
        ]
    )
    rates = {"EUR": 1.0}
    out = convert_benchmark_to_eur(df, rates)
    assert len(out) == 1
    assert out.loc[0, "median_eur"] == 50000.0


def test_convert_empty_frame_passthrough() -> None:
    df = pd.DataFrame(columns=["isco_code", "country", "period", "currency", "median_eur"])
    out = convert_benchmark_to_eur(df, {"EUR": 1.0})
    assert out.empty
