"""Ashby public job-board source adapter.

Endpoint: ``https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=true``

No auth, no pagination. Ashby is the one ATS in this set that frequently exposes
structured compensation data, so this adapter parses it when the currency
matches the country's default (per :data:`jobpipe.fx.COUNTRY_CURRENCY`) and
annualises in the adapter so the downstream FX step does plain numeric
multiplication. Mixed-currency compensation (e.g. USD pay for a Dublin role)
is dropped to avoid spurious EUR conversion.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pandas as pd
from pydantic import Field
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from jobpipe.fx import COUNTRY_CURRENCY
from jobpipe.sources import SourceConfig, SourceFetchError, register
from jobpipe.sources._companies import load_companies_file, match_country

logger = logging.getLogger(__name__)

BASE_URL = "https://api.ashbyhq.com/posting-api/job-board"

INTERVAL_PERIOD_MAP: dict[str, str] = {
    "1 year": "annual",
    "year": "annual",
    "yearly": "annual",
    "annual": "annual",
    "1 month": "monthly",
    "month": "monthly",
    "monthly": "monthly",
    "1 week": "weekly",
    "week": "weekly",
    "weekly": "weekly",
    "1 day": "daily",
    "day": "daily",
    "daily": "daily",
    "1 hour": "hourly",
    "hour": "hourly",
    "hourly": "hourly",
}

ANNUALISE_FACTOR: dict[str, float] = {
    "hourly": 2080.0,
    "daily": 261.0,
    "weekly": 52.0,
    "monthly": 12.0,
    "annual": 1.0,
}


class AshbyConfig(SourceConfig):
    """Ashby public-board config."""

    companies_file: Path = Field(
        description="Path to the YAML file listing per-ATS company slugs.",
    )
    include_compensation: bool = Field(default=True)
    timeout_seconds: float = Field(default=30.0, gt=0)


@register("ashby")
class AshbyAdapter:
    name: str = "ashby"
    config_model: type[SourceConfig] = AshbyConfig

    def fetch(
        self,
        config: SourceConfig,
        *,
        client: httpx.Client | None = None,
    ) -> pd.DataFrame:
        cfg = config if isinstance(config, AshbyConfig) else AshbyConfig(**config.model_dump())
        slugs = load_companies_file(cfg.companies_file, "ashby")
        if not slugs:
            logger.warning("ashby: no slugs configured in %s", cfg.companies_file)
            return pd.DataFrame()

        own_client = client is None
        http = client or httpx.Client(timeout=cfg.timeout_seconds)
        rows: list[dict[str, Any]] = []
        ingested_at = datetime.now(UTC)
        keywords_lower = [k.lower() for k in cfg.keywords] if cfg.keywords else []

        try:
            for slug in slugs:
                rows.extend(self._fetch_one(http, slug, cfg, keywords_lower, ingested_at))
                if len(rows) >= cfg.max_results:
                    break
        finally:
            if own_client:
                http.close()

        df = pd.DataFrame(rows)
        if not df.empty:
            df = df.drop_duplicates(subset="posting_id", keep="first").reset_index(drop=True)
            df = df.head(cfg.max_results)
        return df

    def _fetch_one(
        self,
        http: httpx.Client,
        slug: str,
        cfg: AshbyConfig,
        keywords_lower: list[str],
        ingested_at: datetime,
    ) -> list[dict[str, Any]]:
        payload = self._get_board(http, slug, cfg.include_compensation)
        if payload is None:
            return []
        rows: list[dict[str, Any]] = []
        for job in payload.get("jobs", []):
            row = _normalise_row(job, slug, cfg.countries, ingested_at)
            if row is None:
                continue
            if keywords_lower and not _title_matches(row["title"], keywords_lower):
                continue
            rows.append(row)
        return rows

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(httpx.HTTPError),
        reraise=True,
    )
    def _get_board(
        self,
        http: httpx.Client,
        slug: str,
        include_compensation: bool,
    ) -> dict[str, Any] | None:
        url = f"{BASE_URL}/{slug}"
        params: dict[str, str] = {}
        if include_compensation:
            params["includeCompensation"] = "true"
        try:
            r = http.get(url, params=params)
            if r.status_code == 404:
                logger.warning("ashby: slug %r returned 404, skipping", slug)
                return None
            r.raise_for_status()
        except httpx.HTTPError as exc:
            raise SourceFetchError(f"ashby {slug!r}: {exc}") from exc
        body = r.json()
        if not isinstance(body, dict):
            logger.warning("ashby: slug %r returned non-mapping body, skipping", slug)
            return None
        return body


def _title_matches(title: str, keywords_lower: list[str]) -> bool:
    lo = title.lower()
    return any(k in lo for k in keywords_lower)


def _normalise_row(
    raw: dict[str, Any],
    slug: str,
    allowed_countries: list[str],
    ingested_at: datetime,
) -> dict[str, Any] | None:
    job_id = str(raw.get("id") or "").strip()
    if not job_id:
        return None

    location_text = (raw.get("location") or raw.get("locationName") or "").strip()
    iso2, is_remote_via_text = match_country(location_text, allowed_countries)
    if iso2 is None:
        return None
    is_remote = bool(raw.get("isRemote", False)) or is_remote_via_text

    posting_url = (raw.get("jobUrl") or "").strip()
    if not posting_url.startswith("http"):
        return None

    salary_min, salary_max, salary_period = _extract_compensation(raw.get("compensation"), iso2)

    posting_id = hashlib.sha1(f"ashby:{slug}:{job_id}".encode()).hexdigest()
    posted_at = raw.get("publishedAt") or raw.get("updatedAt") or ingested_at.isoformat()

    return {
        "posting_id": posting_id,
        "source": "ashby",
        "title": (raw.get("title") or "").strip(),
        "company": slug,
        "location_raw": location_text or None,
        "country": iso2,
        "region": None,
        "remote": is_remote,
        # Native-currency values at this stage — FX step in normalise.run() converts to EUR.
        "salary_min_eur": salary_min,
        "salary_max_eur": salary_max,
        "salary_period": salary_period,
        "salary_annual_eur_p50": (
            (salary_min + salary_max) / 2.0
            if salary_min is not None and salary_max is not None
            else None
        ),
        "salary_imputed": False if salary_min is not None else None,
        "posted_at": pd.to_datetime(posted_at, utc=True, errors="coerce"),
        "ingested_at": pd.Timestamp(ingested_at),
        "posting_url": posting_url,
        "isco_code": None,
        "isco_match_method": None,
        "isco_match_score": None,
        "raw_payload": json.dumps(raw, default=str),
    }


def _extract_compensation(
    comp: Any,
    country_iso2: str,
) -> tuple[float | None, float | None, str | None]:
    """Return ``(min_annual_native, max_annual_native, "annual")`` or all-None.

    Only emits when the compensation component's currency matches the country's
    default currency (per ``fx.COUNTRY_CURRENCY``) — mixed-currency comp is
    dropped so the downstream FX step doesn't reinterpret USD as EUR. The
    period is normalised to ``"annual"`` so :func:`jobpipe.normalise.run` can
    treat every Ashby row uniformly.
    """
    if not isinstance(comp, dict):
        return None, None, None
    expected = COUNTRY_CURRENCY.get(country_iso2)
    if expected is None:
        return None, None, None

    for tier in comp.get("compensationTiers") or []:
        if not isinstance(tier, dict):
            continue
        for component in tier.get("components") or []:
            if not isinstance(component, dict):
                continue
            kind = (component.get("componentType") or "").lower()
            if kind not in {"salary", "base salary"}:
                continue
            currency = (component.get("currencyCode") or "").upper()
            if currency != expected:
                continue
            interval = (component.get("interval") or "").strip().lower()
            period = INTERVAL_PERIOD_MAP.get(interval)
            if period is None:
                continue
            min_raw = component.get("minValue")
            max_raw = component.get("maxValue")
            if min_raw is None or max_raw is None:
                continue
            try:
                min_v = float(min_raw)
                max_v = float(max_raw)
            except (TypeError, ValueError):
                continue
            factor = ANNUALISE_FACTOR[period]
            return min_v * factor, max_v * factor, "annual"
    return None, None, None
