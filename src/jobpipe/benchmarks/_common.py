"""Shared helpers for benchmark adapters.

Three pieces, each isolated for unit-test convenience:

* :func:`last_fetch_mtime` — newest parquet under a raw-benchmark directory.
  Side-effecting (touches FS); used by the runner to honour
  ``min_interval_hours``.
* :func:`should_skip` — pure decision: given a clock and the last fetch
  timestamp, do we sleep this adapter for now?
* :func:`convert_benchmark_to_eur` — pure FX conversion for benchmark rows.
  Benchmarks carry an explicit ``currency`` column rather than inferring
  from country (cross-border earnings series exist), so the helper is
  thinner than :func:`jobpipe.fx.convert_to_eur`.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

BENCHMARK_VALUE_COLUMNS: tuple[str, ...] = ("median_eur", "p25_eur", "p75_eur")


def last_fetch_mtime(adapter_dir: Path) -> datetime | None:
    """Return the newest ``*.parquet`` mtime under ``adapter_dir`` (UTC), or None.

    Returns None when the directory is missing or contains no parquet files.
    """
    if not adapter_dir.exists() or not adapter_dir.is_dir():
        return None
    parquets = list(adapter_dir.glob("*.parquet"))
    if not parquets:
        return None
    newest = max(parquets, key=lambda p: p.stat().st_mtime)
    return datetime.fromtimestamp(newest.stat().st_mtime, tz=UTC)


def should_skip(
    now: datetime,
    last_fetch: datetime | None,
    min_interval_hours: int,
) -> bool:
    """Should the runner skip this benchmark's fetch right now?

    ``True`` only when a previous fetch exists AND happened within the
    throttle window. ``min_interval_hours <= 0`` disables throttling.
    """
    if last_fetch is None or min_interval_hours <= 0:
        return False
    return (now - last_fetch) < timedelta(hours=min_interval_hours)


def convert_benchmark_to_eur(df: pd.DataFrame, rates: dict[str, float]) -> pd.DataFrame:
    """Rewrite ``median_eur`` / ``p25_eur`` / ``p75_eur`` from native to EUR.

    ECB rates are quoted as ``1 EUR = rate CCY``; native → EUR therefore
    divides by the rate. Rows whose ``currency`` is missing from ``rates``
    are dropped with a warning — emitting NaN ``median_eur`` would violate
    the strict ``BenchmarkSchema`` (median is non-nullable).

    Sets ``currency`` to ``"EUR"`` on the surviving rows; original currency
    is recoverable from the adapter's ``source_url`` or fixture.
    """
    if df.empty:
        return df.copy()

    out = df.copy()
    currencies = out["currency"].str.upper()
    rate_per_eur = currencies.map(rates).astype(float)

    unresolved = currencies[rate_per_eur.isna()].unique().tolist()
    if unresolved:
        logger.warning(
            "benchmark fx: no ECB rate for %s; %d row(s) dropped",
            sorted(unresolved),
            int(rate_per_eur.isna().sum()),
        )
        keep = rate_per_eur.notna()
        out = out.loc[keep].copy()
        rate_per_eur = rate_per_eur.loc[keep]

    for col in BENCHMARK_VALUE_COLUMNS:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce") / rate_per_eur

    out["currency"] = "EUR"
    return out.reset_index(drop=True)
