"""OECD SDMX-JSON benchmark adapter.

Source: OECD SDMX endpoint at ``https://sdmx.oecd.org/public/rest/data/...``
(SDMX-JSON 2.0 format).

**Operational blocker** — the live endpoint is fronted by Cloudflare's bot-
protection challenge, so an unauthenticated GitHub-Actions worker may receive
HTTP 403 + an HTML interstitial instead of JSON. The adapter handles this
gracefully (logs + returns an empty frame) and ships ``enabled: false`` in
the preset. The follow-up PR that hardens this should either:

* set an ``OECD_API_KEY`` header if the user has one,
* fetch a mirror (e.g. ``data-explorer.oecd.org`` CSV export), or
* run the call through a fixed-egress proxy.

Until then, the adapter is testable against the bundled fixture (which mirrors
the documented SDMX-JSON 2.0 shape) but won't return live data in CI.

Endpoint pattern:
    /public/rest/data/{agency}.{flow}.{version}/{key}?format=jsondata

The ``key`` slot is a dot-delimited dimension filter (use ``..`` for "all").
The parser is generic and reads the dimension metadata from the response, so
new dataflows just need new ``dataflow_id`` / ``key`` settings.
"""

from __future__ import annotations

import logging
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

DEFAULT_BASE = "https://sdmx.oecd.org/public/rest/data"
DEFAULT_DATAFLOW = "OECD.ELS.SAE,DSD_EARNINGS@DF_EAR_MEI,1.0"
DEFAULT_KEY = "all"


class OecdConfig(BenchmarkConfig):
    base_url: str = Field(default=DEFAULT_BASE)
    dataflow_id: str = Field(default=DEFAULT_DATAFLOW)
    key: str = Field(default=DEFAULT_KEY)
    min_interval_hours: int = Field(default=720)  # monthly cadence


@retry(
    retry=retry_if_exception_type(httpx.HTTPError),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    stop=stop_after_attempt(3),
    reraise=True,
)
def _http_get(url: str) -> httpx.Response:
    return httpx.get(
        url,
        headers={"Accept": "application/vnd.sdmx.data+json", "User-Agent": "jobpipe/0.1"},
        timeout=60.0,
    )


def _dimension_values(
    structures: list[dict[str, Any]],
    name: str,
) -> list[dict[str, Any]]:
    for struct in structures:
        observation = (struct.get("dimensions", {}) or {}).get("observation", []) or []
        for dim in observation:
            if dim.get("id", "").upper() == name.upper():
                return list(dim.get("values", []) or [])
    return []


def _attribute_values(
    structures: list[dict[str, Any]],
    name: str,
) -> list[dict[str, Any]]:
    for struct in structures:
        observation = (struct.get("attributes", {}) or {}).get("observation", []) or []
        for attr in observation:
            if attr.get("id", "").upper() == name.upper():
                return list(attr.get("values", []) or [])
    return []


def _parse_dataset(
    payload: dict[str, Any],
    isco_codes: list[str],
    countries: list[str],
    *,
    retrieved_at: datetime,
    source_url: str,
    rates: dict[str, float],
) -> pd.DataFrame:
    data = payload.get("data") or payload
    datasets = data.get("dataSets") or []
    structures = data.get("structures") or ([data["structure"]] if "structure" in data else [])
    if not datasets or not structures:
        return _empty_frame()

    structure = structures[0]
    obs_dims = (structure.get("dimensions", {}) or {}).get("observation", []) or []
    dim_ids = [d.get("id", "") for d in obs_dims]
    dim_value_lists = [list(d.get("values", []) or []) for d in obs_dims]

    obs_attrs = (structure.get("attributes", {}) or {}).get("observation", []) or []
    currency_attr_pos: int | None = None
    for pos, attr in enumerate(obs_attrs):
        if attr.get("id", "").upper() == "UNIT_MEASURE":
            currency_attr_pos = pos
            break
    currency_values = _attribute_values(structures, "UNIT_MEASURE")
    time_values = _dimension_values(structures, "TIME_PERIOD")

    def _resolve_dim(name: str) -> int | None:
        for i, did in enumerate(dim_ids):
            if did.upper() == name.upper():
                return i
        return None

    isco_pos = _resolve_dim("ISCO08") if _resolve_dim("ISCO08") is not None else _resolve_dim("OCC")
    country_pos = _resolve_dim("REF_AREA")
    time_pos = _resolve_dim("TIME_PERIOD")

    if isco_pos is None or country_pos is None:
        logger.warning("oecd: structure missing ISCO/REF_AREA dimensions: %s", dim_ids)
        return _empty_frame()

    requested_isco = set(isco_codes)
    requested_countries = {c.upper() for c in countries}

    rows: list[dict[str, Any]] = []
    observations = datasets[0].get("observations", {}) or {}
    for key_str, values in observations.items():
        positions = [int(p) for p in key_str.split(":") if p]
        if len(positions) != len(dim_ids):
            continue
        isco_code_raw = dim_value_lists[isco_pos][positions[isco_pos]].get("id", "")
        country_raw = dim_value_lists[country_pos][positions[country_pos]].get("id", "").upper()
        period = ""
        if time_pos is not None and dim_value_lists[time_pos]:
            period = dim_value_lists[time_pos][positions[time_pos]].get("id", "")
        elif time_values:
            period = time_values[0].get("id", "")

        if requested_isco and isco_code_raw not in requested_isco:
            continue
        if requested_countries and country_raw not in requested_countries:
            continue
        if not isco_code_raw or not isco_code_raw.isdigit() or len(isco_code_raw) != 4:
            continue

        median = float(values[0]) if values and values[0] is not None else None
        if median is None:
            continue

        currency = "EUR"
        if currency_attr_pos is not None and len(values) > 1 + currency_attr_pos:
            cur_idx = values[1 + currency_attr_pos]
            if isinstance(cur_idx, int) and 0 <= cur_idx < len(currency_values):
                currency = currency_values[cur_idx].get("id", "EUR")

        rows.append(
            {
                "isco_code": isco_code_raw,
                "country": country_raw,
                "period": period or "",
                "currency": currency,
                "median_eur": median,
                "p25_eur": None,
                "p75_eur": None,
                "n_observations": None,
                "source": "oecd",
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


@benchmarks.register("oecd")
class OecdBenchmark:
    name: str = "oecd"
    config_model: type[BenchmarkConfig] = OecdConfig

    def fetch(
        self,
        config: BenchmarkConfig,
        *,
        rates: dict[str, float] | None = None,
    ) -> pd.DataFrame:
        cfg = config if isinstance(config, OecdConfig) else OecdConfig(**config.model_dump())
        url = f"{cfg.base_url}/{cfg.dataflow_id}/{cfg.key}?format=jsondata"
        try:
            r = _http_get(url)
            r.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("oecd: fetch failed for %s: %s", url, exc)
            return _empty_frame()
        if "application/json" not in (r.headers.get("content-type") or "").lower():
            logger.warning(
                "oecd: non-JSON content-type %r — likely Cloudflare interstitial; returning empty",
                r.headers.get("content-type"),
            )
            return _empty_frame()
        try:
            payload = r.json()
        except ValueError as exc:
            logger.warning("oecd: non-JSON body from %s: %s", url, exc)
            return _empty_frame()
        return _parse_dataset(
            payload,
            isco_codes=cfg.isco_codes,
            countries=cfg.countries,
            retrieved_at=datetime.now(UTC),
            source_url=url,
            rates=rates or {"EUR": 1.0},
        )
