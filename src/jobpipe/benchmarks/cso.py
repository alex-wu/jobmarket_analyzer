"""CSO Ireland PxStat benchmark adapter.

Source: CSO ``EHQ03`` cube (Earnings, Hours and Employment Costs Survey,
quarterly) at
``https://ws.cso.ie/public/api.restful/PxStat.Data.Cube_API.ReadDataset/EHQ03/JSON-stat/2.0/en``.

Important caveat documented in the preset's YAML: CSO does NOT publish
quarterly earnings by 4-digit ISCO. The cube uses a 3-bucket "Type of
Employee" axis (``C02397V02888``):

* ``1`` — Managers, professionals and associated professionals (ISCO 1xx/2xx/3xx)
* ``2`` — Clerical, sales and service employees (ISCO 4xx/5xx)
* ``3`` — Production, transport, craft and other manual workers (ISCO 6xx-9xx)

The adapter therefore emits one benchmark row per *requested* ISCO code,
mapped to the relevant umbrella bucket. The preset's ``isco_focus`` codes
(2511, 2521, 2423) all collapse to bucket 1. Document this coarseness when
surfacing in the dashboard.

Native currency is EUR — no FX conversion needed. Weekly earnings are
annualised in-adapter (``x52``).
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

logger = logging.getLogger(__name__)

DEFAULT_DATASET = "EHQ03"
DEFAULT_STATISTIC = "EHQ03C02"  # Average Weekly Earnings
DEFAULT_SECTOR = "-"  # All NACE economic sectors
ENDPOINT_TEMPLATE = (
    "https://ws.cso.ie/public/api.restful/"
    "PxStat.Data.Cube_API.ReadDataset/{dataset}/JSON-stat/2.0/en"
)


def _isco_to_cso_bucket(isco_code: str) -> str | None:
    """Map a 4-digit ISCO-08 code to CSO ``C02397V02888`` bucket id."""
    if not isco_code or not isco_code[0].isdigit():
        return None
    major = isco_code[0]
    if major in ("1", "2", "3"):
        return "1"
    if major in ("4", "5"):
        return "2"
    if major in ("6", "7", "8", "9"):
        return "3"
    return None


class CsoConfig(BenchmarkConfig):
    dataset_code: str = Field(default=DEFAULT_DATASET)
    statistic: str = Field(default=DEFAULT_STATISTIC)
    sector: str = Field(default=DEFAULT_SECTOR)
    min_interval_hours: int = Field(default=168)  # weekly


def _strides(sizes: list[int]) -> list[int]:
    """Row-major strides for a flat JSON-stat ``value`` list."""
    strides: list[int] = [1] * len(sizes)
    for i in range(len(sizes) - 2, -1, -1):
        strides[i] = strides[i + 1] * sizes[i + 1]
    return strides


def _index_of(category: dict[str, Any], code: str) -> int | None:
    """Resolve a category code to its positional index in a JSON-stat dimension."""
    idx = category.get("index")
    if isinstance(idx, list):
        try:
            return idx.index(code)
        except ValueError:
            return None
    if isinstance(idx, dict):
        return idx.get(code)
    return None


def _value_at(
    values: list[float] | dict[str, float],
    coords: list[int],
    strides: list[int],
) -> float | None:
    """Read one value from a JSON-stat flat array given coords + strides."""
    flat = sum(c * s for c, s in zip(coords, strides, strict=False))
    if isinstance(values, list):
        if 0 <= flat < len(values):
            v = values[flat]
            return float(v) if v is not None else None
        return None
    raw = values.get(str(flat))
    return float(raw) if raw is not None else None


def _latest_period(dim_id_to_idx: dict[str, int]) -> str | None:
    """Pick the newest period code from a TLIST(Q1) dimension index list."""
    if not dim_id_to_idx:
        return None
    return max(dim_id_to_idx, key=dim_id_to_idx.get)  # type: ignore[arg-type]


@retry(
    retry=retry_if_exception_type(httpx.HTTPError),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    stop=stop_after_attempt(3),
    reraise=True,
)
def _http_get(url: str) -> httpx.Response:
    return httpx.get(
        url,
        headers={"Accept": "application/json", "User-Agent": "jobpipe/0.1"},
        timeout=60.0,
    )


def _parse_dataset(
    payload: dict[str, Any],
    config: CsoConfig,
    isco_codes: list[str],
    countries: list[str],
    *,
    retrieved_at: datetime,
    source_url: str,
) -> pd.DataFrame:
    """Pure JSON-stat parser → BenchmarkSchema rows."""
    dim_ids: list[str] = payload.get("id", []) or []
    sizes: list[int] = payload.get("size", []) or []
    if not dim_ids or len(dim_ids) != len(sizes):
        return _empty_frame()

    strides = _strides(sizes)
    dimensions = payload.get("dimension", {}) or {}
    values = payload.get("value", []) or []

    # Resolve the four CSO dimensions by id.
    time_dim_id = next((d for d in dim_ids if d.startswith("TLIST")), None)
    if time_dim_id is None:
        logger.warning("cso: response has no TLIST dimension")
        return _empty_frame()
    stat_dim = dimensions.get("STATISTIC", {}).get("category", {})
    time_dim = dimensions.get(time_dim_id, {}).get("category", {})
    sector_dim_id = "C02665V03225"
    sector_dim = dimensions.get(sector_dim_id, {}).get("category", {})
    emp_dim_id = "C02397V02888"
    emp_dim = dimensions.get(emp_dim_id, {}).get("category", {})

    stat_idx = _index_of(stat_dim, config.statistic)
    sector_idx = _index_of(sector_dim, config.sector)
    if stat_idx is None or sector_idx is None:
        logger.warning(
            "cso: required code missing — stat=%s sector=%s",
            config.statistic,
            config.sector,
        )
        return _empty_frame()

    time_index_map = time_dim.get("index", {}) or {}
    if isinstance(time_index_map, list):
        time_index_map = {code: pos for pos, code in enumerate(time_index_map)}
    latest_period = _latest_period(time_index_map)
    if latest_period is None:
        return _empty_frame()
    time_idx = time_index_map[latest_period]

    # Pre-compute bucket → emp index once per dataset.
    bucket_to_idx: dict[str, int] = {}
    for bucket_code in ("1", "2", "3"):
        idx = _index_of(emp_dim, bucket_code)
        if idx is not None:
            bucket_to_idx[bucket_code] = idx

    rows: list[dict[str, Any]] = []
    countries_upper = [c.upper() for c in countries] or ["IE"]

    for country in countries_upper:
        if country != "IE":
            logger.info("cso: country=%s skipped (cube is IE-only)", country)
            continue
        for isco_code in isco_codes:
            bucket = _isco_to_cso_bucket(isco_code)
            if bucket is None or bucket not in bucket_to_idx:
                continue
            coords = [0] * len(dim_ids)
            coords[dim_ids.index("STATISTIC")] = stat_idx
            coords[dim_ids.index(time_dim_id)] = time_idx
            coords[dim_ids.index(sector_dim_id)] = sector_idx
            coords[dim_ids.index(emp_dim_id)] = bucket_to_idx[bucket]
            weekly = _value_at(values, coords, strides)
            if weekly is None:
                continue
            annual = float(weekly) * 52.0
            rows.append(
                {
                    "isco_code": isco_code,
                    "country": country,
                    "period": latest_period,
                    "currency": "EUR",
                    "median_eur": annual,
                    "p25_eur": None,
                    "p75_eur": None,
                    "n_observations": None,
                    "source": "cso",
                    "source_url": source_url,
                    "retrieved_at": pd.Timestamp(retrieved_at),
                }
            )
    if not rows:
        return _empty_frame()
    df = pd.DataFrame(rows)
    df["n_observations"] = df["n_observations"].astype("Int64")
    df["retrieved_at"] = pd.to_datetime(df["retrieved_at"], utc=True)
    return df


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


@benchmarks.register("cso")
class CsoBenchmark:
    name: str = "cso"
    config_model: type[BenchmarkConfig] = CsoConfig

    def fetch(
        self,
        config: BenchmarkConfig,
        *,
        rates: dict[str, float] | None = None,  # accepted but unused — CSO is EUR-native
    ) -> pd.DataFrame:
        cfg = config if isinstance(config, CsoConfig) else CsoConfig(**config.model_dump())
        url = ENDPOINT_TEMPLATE.format(dataset=cfg.dataset_code)
        try:
            r = _http_get(url)
            r.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("cso: fetch failed for %s: %s", url, exc)
            return _empty_frame()
        try:
            payload = r.json()
        except ValueError as exc:
            logger.warning("cso: non-JSON response from %s: %s", url, exc)
            return _empty_frame()
        return _parse_dataset(
            payload,
            cfg,
            isco_codes=cfg.isco_codes,
            countries=cfg.countries,
            retrieved_at=datetime.now(UTC),
            source_url=url,
        )
