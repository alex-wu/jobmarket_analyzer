"""Lever public-postings source adapter.

Endpoint: ``https://api.lever.co/v0/postings/{slug}?mode=json``

No auth, no pagination. The response body is a JSON array of postings (not
wrapped in an envelope). Per-slug 404s are tolerated so a stale slug does not
abort the whole run.
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

BASE_URL = "https://api.lever.co/v0/postings"


class LeverConfig(SourceConfig):
    """Lever public-postings config."""

    companies_file: Path = Field(
        description="Path to the YAML file listing per-ATS company slugs.",
    )
    timeout_seconds: float = Field(default=30.0, gt=0)


@register("lever")
class LeverAdapter:
    name: str = "lever"
    config_model: type[SourceConfig] = LeverConfig

    def fetch(
        self,
        config: SourceConfig,
        *,
        client: httpx.Client | None = None,
    ) -> pd.DataFrame:
        cfg = config if isinstance(config, LeverConfig) else LeverConfig(**config.model_dump())
        slugs = load_companies_file(cfg.companies_file, "lever")
        if not slugs:
            logger.warning("lever: no slugs configured in %s", cfg.companies_file)
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
        cfg: LeverConfig,
        keywords_lower: list[str],
        ingested_at: datetime,
    ) -> list[dict[str, Any]]:
        payload = self._get_postings(http, slug)
        if payload is None:
            return []
        rows: list[dict[str, Any]] = []
        for posting in payload:
            row = _normalise_row(posting, slug, cfg.countries, ingested_at)
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
    def _get_postings(self, http: httpx.Client, slug: str) -> list[dict[str, Any]] | None:
        url = f"{BASE_URL}/{slug}"
        try:
            r = http.get(url, params={"mode": "json"})
            if r.status_code == 404:
                logger.warning("lever: slug %r returned 404, skipping", slug)
                return None
            r.raise_for_status()
        except httpx.HTTPError as exc:
            raise SourceFetchError(f"lever {slug!r}: {exc}") from exc
        body = r.json()
        if not isinstance(body, list):
            logger.warning("lever: slug %r returned non-list body, skipping", slug)
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
    posting_id_raw = str(raw.get("id") or "").strip()
    if not posting_id_raw:
        return None

    categories = raw.get("categories") or {}
    location_text = (categories.get("location") or "").strip()
    iso2, is_remote = match_country(location_text, allowed_countries)
    if iso2 is None:
        return None

    posting_url = (raw.get("hostedUrl") or raw.get("applyUrl") or "").strip()
    if not posting_url.startswith("http"):
        return None

    posting_id = hashlib.sha1(f"lever:{slug}:{posting_id_raw}".encode()).hexdigest()
    posted_at_raw = raw.get("createdAt")
    if isinstance(posted_at_raw, int | float):
        posted_at: Any = pd.to_datetime(int(posted_at_raw), unit="ms", utc=True, errors="coerce")
    else:
        posted_at = pd.to_datetime(
            posted_at_raw or ingested_at.isoformat(), utc=True, errors="coerce"
        )

    return {
        "posting_id": posting_id,
        "source": "lever",
        "title": (raw.get("text") or "").strip(),
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
        "posted_at": posted_at,
        "ingested_at": pd.Timestamp(ingested_at),
        "posting_url": posting_url,
        "isco_code": None,
        "isco_match_method": None,
        "isco_match_score": None,
        "raw_payload": json.dumps(raw, default=str),
    }
