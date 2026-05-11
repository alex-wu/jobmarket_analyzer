"""Greenhouse public job-board source adapter.

Endpoint: ``https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true``

No auth, no pagination — one HTTP call per company board returns the full
posting list. The list of board slugs to query comes from
``config/companies/<file>.yaml`` (see :mod:`jobpipe.sources._companies`).
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

from jobpipe.sources import SourceConfig, SourceFetchError, register
from jobpipe.sources._companies import load_companies_file, match_country

logger = logging.getLogger(__name__)

BASE_URL = "https://boards-api.greenhouse.io/v1/boards"


class GreenhouseConfig(SourceConfig):
    """Greenhouse public-board config.

    Inherits ``keywords``/``countries``/``max_results`` from :class:`SourceConfig`.
    """

    companies_file: Path = Field(
        description="Path to the YAML file listing per-ATS company slugs.",
    )
    timeout_seconds: float = Field(default=30.0, gt=0)


@register("greenhouse")
class GreenhouseAdapter:
    """Pulls postings from every slug in the companies file."""

    name: str = "greenhouse"
    config_model: type[SourceConfig] = GreenhouseConfig

    def fetch(
        self,
        config: SourceConfig,
        *,
        client: httpx.Client | None = None,
    ) -> pd.DataFrame:
        cfg = (
            config
            if isinstance(config, GreenhouseConfig)
            else GreenhouseConfig(**config.model_dump())
        )
        slugs = load_companies_file(cfg.companies_file, "greenhouse")
        if not slugs:
            logger.warning("greenhouse: no slugs configured in %s", cfg.companies_file)
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
        cfg: GreenhouseConfig,
        keywords_lower: list[str],
        ingested_at: datetime,
    ) -> list[dict[str, Any]]:
        payload = self._get_board(http, slug)
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
    def _get_board(self, http: httpx.Client, slug: str) -> dict[str, Any] | None:
        """Fetch one board. ``None`` on 404 (let the run continue with other slugs)."""
        url = f"{BASE_URL}/{slug}/jobs"
        try:
            r = http.get(url, params={"content": "true"})
            if r.status_code == 404:
                logger.warning("greenhouse: slug %r returned 404, skipping", slug)
                return None
            r.raise_for_status()
        except httpx.HTTPError as exc:
            raise SourceFetchError(f"greenhouse {slug!r}: {exc}") from exc
        return r.json()  # type: ignore[no-any-return]


def _title_matches(title: str, keywords_lower: list[str]) -> bool:
    lo = title.lower()
    return any(k in lo for k in keywords_lower)


def _normalise_row(
    raw: dict[str, Any],
    slug: str,
    allowed_countries: list[str],
    ingested_at: datetime,
) -> dict[str, Any] | None:
    """Map one Greenhouse job to a PostingSchema row, or ``None`` if filtered out."""
    job_id = str(raw.get("id") or "").strip()
    if not job_id:
        return None

    location_text = ((raw.get("location") or {}).get("name")) or ""
    if not location_text:
        offices = raw.get("offices") or []
        if offices:
            first = offices[0] or {}
            location_text = first.get("location") or first.get("name") or ""

    iso2, is_remote = match_country(location_text, allowed_countries)
    if iso2 is None:
        return None

    posting_url = (raw.get("absolute_url") or "").strip()
    if not posting_url.startswith("http"):
        # PostingSchema requires a valid http(s) URL — drop malformed rows.
        return None

    posting_id = hashlib.sha1(f"greenhouse:{slug}:{job_id}".encode()).hexdigest()
    posted_at = raw.get("updated_at") or ingested_at.isoformat()

    return {
        "posting_id": posting_id,
        "source": "greenhouse",
        "title": (raw.get("title") or "").strip(),
        "company": slug,
        "location_raw": location_text or None,
        "country": iso2,
        "region": None,
        "remote": is_remote,
        "salary_min_eur": None,
        "salary_max_eur": None,
        "salary_period": None,
        "salary_annual_eur_p50": None,
        "salary_imputed": None,
        "posted_at": pd.to_datetime(posted_at, utc=True, errors="coerce"),
        "ingested_at": pd.Timestamp(ingested_at),
        "posting_url": posting_url,
        "isco_code": None,
        "isco_match_method": None,
        "isco_match_score": None,
        "raw_payload": json.dumps(raw, default=str),
    }
