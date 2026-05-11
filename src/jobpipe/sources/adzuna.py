"""Adzuna source adapter.

Endpoint: ``https://api.adzuna.com/v1/api/jobs/{country}/search/{page}``

Free-tier rate limits are not publicly documented; this adapter caps itself
conservatively at ``max_pages * results_per_page`` per ``fetch`` call. Use the
preset's ``min_interval_hours`` knob (honoured by the refresh workflow) to
throttle across runs.

Country coverage in 2026 (from public country pages): at, au, be, br, ca, ch,
de, es, fr, gb, in, it, mx, nl, nz, pl, sg, us, za. **Ireland (``ie``) is not
served** — for IE-focused analysis pair this adapter with the ATS adapters
(Greenhouse / Lever / Ashby / Personio, landing in P3) or with Remotive.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

import httpx
import pandas as pd
from pydantic import Field
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from jobpipe.settings import settings
from jobpipe.sources import SourceConfig, SourceFetchError, register

BASE_URL = "https://api.adzuna.com/v1/api/jobs"


class AdzunaConfig(SourceConfig):
    """Adzuna search-endpoint config.

    Inherits ``enabled`` / ``keywords`` / ``countries`` / ``max_results`` from
    :class:`SourceConfig`. Adzuna treats each ``(country, keyword)`` pair as a
    separate search.
    """

    results_per_page: int = Field(default=50, ge=1, le=50)
    max_pages: int = Field(default=5, ge=1, le=20)
    timeout_seconds: float = Field(default=30.0, gt=0)
    min_interval_hours: int = Field(
        default=24,
        ge=0,
        description="Honoured by the refresh workflow when scheduling.",
    )


@register("adzuna")
class AdzunaAdapter:
    """Pulls postings from Adzuna's public search endpoint."""

    name: str = "adzuna"
    config_model: type[SourceConfig] = AdzunaConfig

    def fetch(
        self,
        config: SourceConfig,
        *,
        client: httpx.Client | None = None,
    ) -> pd.DataFrame:
        """Fetch postings for every (country, keyword) in ``config``.

        ``client`` is dependency-injected so tests can pass a ``MockTransport``.
        """
        cfg = config if isinstance(config, AdzunaConfig) else AdzunaConfig(**config.model_dump())

        if not settings.adzuna_app_id or not settings.adzuna_app_key:
            raise SourceFetchError("adzuna: missing ADZUNA_APP_ID / ADZUNA_APP_KEY in environment")

        own_client = client is None
        http = client or httpx.Client(timeout=cfg.timeout_seconds)
        rows: list[dict[str, Any]] = []
        ingested_at = datetime.now(UTC)

        try:
            for country in cfg.countries:
                for keyword in cfg.keywords:
                    rows.extend(self._fetch_one(http, cfg, country, keyword, ingested_at))
                    if len(rows) >= cfg.max_results:
                        break
                if len(rows) >= cfg.max_results:
                    break
        finally:
            if own_client:
                http.close()

        df = pd.DataFrame(rows)
        if not df.empty:
            # A single Adzuna posting can match multiple keywords; collapse within-source dupes
            # so PostingSchema's posting_id uniqueness check passes. Cross-source dedupe is P2.
            df = df.drop_duplicates(subset="posting_id", keep="first").reset_index(drop=True)
            df = df.head(cfg.max_results)
        return df

    def _fetch_one(
        self,
        http: httpx.Client,
        cfg: AdzunaConfig,
        country: str,
        keyword: str,
        ingested_at: datetime,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for page in range(1, cfg.max_pages + 1):
            payload = self._get_page(http, cfg, country, keyword, page)
            results = payload.get("results", [])
            if not results:
                break
            rows.extend(_normalise_row(r, country, ingested_at) for r in results)
            if len(results) < cfg.results_per_page:
                break
        return rows

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(httpx.HTTPError),
        reraise=True,
    )
    def _get_page(
        self,
        http: httpx.Client,
        cfg: AdzunaConfig,
        country: str,
        keyword: str,
        page: int,
    ) -> dict[str, Any]:
        url = f"{BASE_URL}/{country}/search/{page}"
        params: dict[str, str | int] = {
            "app_id": settings.adzuna_app_id,
            "app_key": settings.adzuna_app_key,
            "what": keyword,
            "results_per_page": cfg.results_per_page,
            "content-type": "application/json",
        }
        try:
            r = http.get(url, params=params)
            r.raise_for_status()
        except httpx.HTTPError as exc:
            raise SourceFetchError(f"adzuna {country!r} page={page}: {exc}") from exc
        return r.json()  # type: ignore[no-any-return]


def _normalise_row(
    raw: dict[str, Any],
    country: str,
    ingested_at: datetime,
) -> dict[str, Any]:
    """Map one Adzuna result to a PostingSchema row.

    Salary fields are left in their native currency at this stage —
    :mod:`jobpipe.normalise` converts to EUR (P2).
    """
    external_id = str(raw.get("id", ""))
    posting_id = hashlib.sha1(f"adzuna:{external_id}".encode()).hexdigest()
    company = (raw.get("company") or {}).get("display_name")
    location = (raw.get("location") or {}).get("display_name")
    salary_min = raw.get("salary_min")
    salary_max = raw.get("salary_max")
    posted_at = raw.get("created") or ingested_at.isoformat()

    return {
        "posting_id": posting_id,
        "source": "adzuna",
        "title": raw.get("title", "").strip(),
        "company": company,
        "location_raw": location,
        "country": country.upper(),
        "region": None,
        "remote": None,
        # Salary is in native currency here; FX conversion happens in normalise.run().
        "salary_min_eur": float(salary_min) if salary_min is not None else None,
        "salary_max_eur": float(salary_max) if salary_max is not None else None,
        "salary_period": "annual",
        "salary_annual_eur_p50": (
            (float(salary_min) + float(salary_max)) / 2
            if salary_min is not None and salary_max is not None
            else None
        ),
        "posted_at": pd.to_datetime(posted_at, utc=True, errors="coerce"),
        "ingested_at": pd.Timestamp(ingested_at),
        "posting_url": raw.get("redirect_url", ""),
        "isco_code": None,
        "isco_match_method": None,
        "isco_match_score": None,
        "raw_payload": json.dumps(raw, default=str),
    }
