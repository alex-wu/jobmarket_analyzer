"""Eurostat SES benchmark adapter (``earn_ses_annual``).

Source: Eurostat Structure of Earnings Survey, annual earnings cube,
served as JSON-stat 2.0 from
``https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/earn_ses_annual``.

Dimensions present: ``freq``, ``nace_r2``, ``isco08``, ``worktime``, ``age``,
``sex``, ``indic_se``, ``geo``, ``time``. The SES is rebased every four years
so ``time`` carries vintages ``2002 / 2006 / 2010 / 2014 / 2018 / 2022``; the
adapter selects the most recent vintage in the response. Caveat: the SES lag
is ~4 years — surface this in the dashboard rather than silently presenting
old numbers as current.

ISCO coding: Eurostat ships codes like ``OC1``, ``OC25``, ``OC2511``. The
adapter strips the ``OC`` prefix and keeps only rows whose remaining code is
exactly 4 digits, because the strict ``PostingSchema`` (and the dashboard
join) expects 4-digit ISCO-08.

Currency: rows are requested at ``unit=EUR``, so no FX conversion runs.
``convert_benchmark_to_eur`` is invoked anyway as a defence-in-depth pass for
fixtures that ship in foreign currency.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Any

import httpx
import pandas as pd
from pydantic import Field
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from jobpipe import benchmarks
from jobpipe.benchmarks import BenchmarkConfig
from jobpipe.benchmarks._common import convert_benchmark_to_eur

logger = logging.getLogger(__name__)

DEFAULT_DATASET = "earn_ses_annual"
ENDPOINT_TEMPLATE = "https://ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/{dataset}"
ISCO_PREFIX_RE = re.compile(r"^OC(\d{4})$")


class EurostatConfig(BenchmarkConfig):
    dataset: str = Field(default=DEFAULT_DATASET)
    indic_se: str = Field(default="MEAN_E_EUR")  # mean annual earnings in EUR
    sex: str = Field(default="T")
    worktime: str = Field(default="FT")
    age: str = Field(default="TOTAL")
    nace_r2: str = Field(default="B-S_X_O")
    min_interval_hours: int = Field(default=720)  # monthly cadence


def _category_index_map(category: dict[str, Any]) -> dict[str, int]:
    idx = category.get("index", {}) or {}
    if isinstance(idx, dict):
        return {code: int(pos) for code, pos in idx.items()}
    if isinstance(idx, list):
        return {code: pos for pos, code in enumerate(idx)}
    return {}


def _strides(sizes: list[int]) -> list[int]:
    strides: list[int] = [1] * len(sizes)
    for i in range(len(sizes) - 2, -1, -1):
        strides[i] = strides[i + 1] * sizes[i + 1]
    return strides


def _value_at(
    values: list[float] | dict[str, float],
    coords: list[int],
    strides: list[int],
) -> float | None:
    flat = sum(c * s for c, s in zip(coords, strides, strict=False))
    if isinstance(values, list):
        if 0 <= flat < len(values):
            v = values[flat]
            return float(v) if v is not None else None
        return None
    raw = values.get(str(flat))
    return float(raw) if raw is not None else None


@retry(
    retry=retry_if_exception_type(httpx.HTTPError),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    stop=stop_after_attempt(3),
    reraise=True,
)
def _http_get(url: str, params: dict[str, str]) -> httpx.Response:
    return httpx.get(
        url,
        params=params,
        headers={"Accept": "application/json", "User-Agent": "jobpipe/0.1"},
        timeout=60.0,
    )


def _parse_dataset(
    payload: dict[str, Any],
    isco_codes: list[str],
    countries: list[str],
    *,
    retrieved_at: datetime,
    source_url: str,
    rates: dict[str, float],
) -> pd.DataFrame:
    dim_ids: list[str] = payload.get("id", []) or []
    sizes: list[int] = payload.get("size", []) or []
    if not dim_ids or len(dim_ids) != len(sizes):
        return _empty_frame()

    strides = _strides(sizes)
    dimensions = payload.get("dimension", {}) or {}
    values = payload.get("value", []) or []

    dim_positions = {d: i for i, d in enumerate(dim_ids)}
    if "isco08" not in dim_positions or "geo" not in dim_positions:
        logger.warning("eurostat: response missing isco08/geo dimensions: %s", dim_ids)
        return _empty_frame()

    isco_cat = _category_index_map(dimensions.get("isco08", {}).get("category", {}))
    geo_cat = _category_index_map(dimensions.get("geo", {}).get("category", {}))
    time_cat = _category_index_map(dimensions.get("time", {}).get("category", {}))

    # Pick the newest vintage we have.
    latest_period: str | None = max(time_cat, key=time_cat.get) if time_cat else None  # type: ignore[arg-type]
    if latest_period is None:
        return _empty_frame()

    requested_isco = set(isco_codes)
    requested_countries = {c.upper() for c in countries}

    # Resolve which isco08 codes (post-prefix-strip) map to 4-digit ISCO.
    isco_eurostat_to_4d: dict[str, str] = {}
    for raw_code in isco_cat:
        m = ISCO_PREFIX_RE.match(raw_code)
        if not m:
            continue
        four_digit = m.group(1)
        if not requested_isco or four_digit in requested_isco:
            isco_eurostat_to_4d[raw_code] = four_digit

    if not isco_eurostat_to_4d:
        logger.info("eurostat: no requested ISCO codes present in response")
        return _empty_frame()

    rows: list[dict[str, Any]] = []
    coords: list[int] = [0] * len(dim_ids)
    coords[dim_positions["time"]] = time_cat[latest_period]

    # Pin every non-(isco/geo/time) dimension to position 0 — Eurostat responses
    # honour query filters, so each of those dims should have size 1 in practice.
    for dim_id, pos in dim_positions.items():
        if dim_id in ("isco08", "geo", "time"):
            continue
        coords[pos] = 0

    for raw_iso, four_d in isco_eurostat_to_4d.items():
        coords[dim_positions["isco08"]] = isco_cat[raw_iso]
        for geo_code, geo_idx in geo_cat.items():
            geo_up = geo_code.upper()
            if requested_countries and geo_up not in requested_countries:
                continue
            coords[dim_positions["geo"]] = geo_idx
            value = _value_at(values, coords, strides)
            if value is None:
                continue
            rows.append(
                {
                    "isco_code": four_d,
                    "country": geo_up,
                    "period": latest_period,
                    "currency": "EUR",
                    "median_eur": float(value),
                    "p25_eur": None,
                    "p75_eur": None,
                    "n_observations": None,
                    "source": "eurostat",
                    "source_url": source_url,
                    "retrieved_at": pd.Timestamp(retrieved_at),
                }
            )

    if not rows:
        return _empty_frame()
    df = pd.DataFrame(rows)
    df["n_observations"] = df["n_observations"].astype("Int64")
    df["retrieved_at"] = pd.to_datetime(df["retrieved_at"], utc=True)
    return convert_benchmark_to_eur(df, rates)


def _empty_frame() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "isco_code",
            "country",
            "period",
            "currency",
            "median_eur",
            "p25_eur",
            "p75_eur",
            "n_observations",
            "source",
            "source_url",
            "retrieved_at",
        ]
    )


@benchmarks.register("eurostat")
class EurostatBenchmark:
    name: str = "eurostat"
    config_model: type[BenchmarkConfig] = EurostatConfig

    def fetch(
        self,
        config: BenchmarkConfig,
        *,
        rates: dict[str, float] | None = None,
    ) -> pd.DataFrame:
        cfg = (
            config if isinstance(config, EurostatConfig) else EurostatConfig(**config.model_dump())
        )
        url = ENDPOINT_TEMPLATE.format(dataset=cfg.dataset)
        params: dict[str, str] = {
            "format": "JSON",
            "lang": "EN",
            "unit": "EUR",
            "sex": cfg.sex,
            "worktime": cfg.worktime,
            "age": cfg.age,
            "nace_r2": cfg.nace_r2,
            "indic_se": cfg.indic_se,
        }
        if cfg.countries:
            params["geo"] = ",".join(c.upper() for c in cfg.countries)

        try:
            r = _http_get(url, params)
            r.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("eurostat: fetch failed for %s: %s", url, exc)
            return _empty_frame()
        try:
            payload = r.json()
        except ValueError as exc:
            logger.warning("eurostat: non-JSON body from %s: %s", url, exc)
            return _empty_frame()
        return _parse_dataset(
            payload,
            isco_codes=cfg.isco_codes,
            countries=cfg.countries,
            retrieved_at=datetime.now(UTC),
            source_url=url,
            rates=rates or {"EUR": 1.0},
        )
