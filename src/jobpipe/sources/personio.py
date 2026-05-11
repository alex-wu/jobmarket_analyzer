"""Personio public XML job-feed source adapter.

Endpoint: ``https://{slug}.jobs.personio.de/xml`` (yes, ``.de`` even for
Ireland-based companies — that's Personio's feed convention).

The feed is XML in the ``workzag-jobs/position`` schema. Parsed with
:mod:`defusedxml` so external feeds can't trigger entity-expansion or external
DTD attacks. Per-slug HTTP 404s and XML parse errors are tolerated so a
single bad feed doesn't abort the run.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import defusedxml.ElementTree as DefusedET
import httpx
import pandas as pd
from pydantic import Field
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from jobpipe.sources import SourceConfig, SourceFetchError, register
from jobpipe.sources._companies import load_companies_file, match_country

if TYPE_CHECKING:
    # Type-only — defusedxml.fromstring returns stdlib Element instances.
    from xml.etree.ElementTree import Element

logger = logging.getLogger(__name__)


class PersonioConfig(SourceConfig):
    """Personio XML-feed config."""

    companies_file: Path = Field(
        description="Path to the YAML file listing per-ATS company slugs.",
    )
    timeout_seconds: float = Field(default=30.0, gt=0)


@register("personio")
class PersonioAdapter:
    name: str = "personio"
    config_model: type[SourceConfig] = PersonioConfig

    def fetch(
        self,
        config: SourceConfig,
        *,
        client: httpx.Client | None = None,
    ) -> pd.DataFrame:
        cfg = (
            config if isinstance(config, PersonioConfig) else PersonioConfig(**config.model_dump())
        )
        slugs = load_companies_file(cfg.companies_file, "personio")
        if not slugs:
            logger.warning("personio: no slugs configured in %s", cfg.companies_file)
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
        cfg: PersonioConfig,
        keywords_lower: list[str],
        ingested_at: datetime,
    ) -> list[dict[str, Any]]:
        xml_text = self._get_feed(http, slug)
        if xml_text is None:
            return []
        try:
            root = DefusedET.fromstring(xml_text)
        except DefusedET.ParseError as exc:
            logger.warning("personio: slug %r XML parse error: %s; skipping", slug, exc)
            return []

        rows: list[dict[str, Any]] = []
        for position in root.findall("position"):
            row = _normalise_row(position, slug, cfg.countries, ingested_at)
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
    def _get_feed(self, http: httpx.Client, slug: str) -> str | None:
        url = f"https://{slug}.jobs.personio.de/xml"
        try:
            r = http.get(url)
            if r.status_code == 404:
                logger.warning("personio: slug %r returned 404, skipping", slug)
                return None
            r.raise_for_status()
        except httpx.HTTPError as exc:
            raise SourceFetchError(f"personio {slug!r}: {exc}") from exc
        return r.text


def _title_matches(title: str, keywords_lower: list[str]) -> bool:
    lo = title.lower()
    return any(k in lo for k in keywords_lower)


def _normalise_row(
    position: Element,
    slug: str,
    allowed_countries: list[str],
    ingested_at: datetime,
) -> dict[str, Any] | None:
    pos_id = (position.findtext("id") or "").strip()
    if not pos_id:
        return None

    office = (position.findtext("office") or "").strip()
    iso2, is_remote = match_country(office, allowed_countries)
    if iso2 is None:
        return None

    title = (position.findtext("name") or "").strip()
    if not title:
        return None

    posting_url = f"https://{slug}.jobs.personio.de/job/{pos_id}"
    posted_at_raw = (position.findtext("createDate") or "").strip()
    if posted_at_raw:
        posted_at = pd.to_datetime(posted_at_raw, utc=True, errors="coerce")
        if pd.isna(posted_at):
            posted_at = pd.Timestamp(ingested_at)
    else:
        posted_at = pd.Timestamp(ingested_at)

    posting_id = hashlib.sha1(f"personio:{slug}:{pos_id}".encode()).hexdigest()
    raw_payload = DefusedET.tostring(position, encoding="unicode")

    return {
        "posting_id": posting_id,
        "source": "personio",
        "title": title,
        "company": slug,
        "location_raw": office or None,
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
        "raw_payload": raw_payload,
    }
