"""Cross-source dedupe.

Primary key: sha1 of normalised URL. Falls back to sha1 of
``title|company|country`` when the URL is missing or empty. v1 Adzuna always
emits a URL, but the fallback exists for future ATS / community adapters
where a canonical URL may be absent.

Within-source dedupe still lives in the adapter (the Adzuna adapter
collapses duplicates from overlapping keyword searches before returning);
this module is the second, cross-source pass.
"""

from __future__ import annotations

import hashlib
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import pandas as pd

# Tracking params we always strip before hashing — they vary between
# referrers but point to the same posting.
_TRACKING_PREFIXES: tuple[str, ...] = ("utm_",)
_TRACKING_NAMES: frozenset[str] = frozenset(
    {
        "fbclid",
        "gclid",
        "mc_cid",
        "mc_eid",
        "igshid",
        "yclid",
        "_hsenc",
        "_hsmi",
        "ref",
        "ref_src",
        "source",
    }
)


def normalise_url(url: str) -> str:
    """Return a canonical-ish URL for hash collapse.

    - Lowercase scheme + host.
    - Drop ``utm_*`` and common tracking query params.
    - Drop trailing slash from the path and any fragment.
    """
    if not url:
        return ""
    parsed = urlparse(url.strip())
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/")
    kept_pairs = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=True)
        if not k.lower().startswith(_TRACKING_PREFIXES) and k.lower() not in _TRACKING_NAMES
    ]
    query = urlencode(kept_pairs)
    return urlunparse((parsed.scheme.lower(), netloc, path, parsed.params, query, ""))


def _safe_str(value: Any) -> str:
    """Coerce a possibly-NaN value to a clean string (NaN → ``''``)."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value)


def posting_hash(row: pd.Series[Any]) -> str:
    """Hash a posting row. URL-based when available, ``title|company|country`` otherwise."""
    url = normalise_url(_safe_str(row.get("posting_url")))
    if url:
        return hashlib.sha1(f"url:{url}".encode()).hexdigest()
    title = _safe_str(row.get("title")).strip().lower()
    company = _safe_str(row.get("company")).strip().lower()
    country = _safe_str(row.get("country")).strip().lower()
    return hashlib.sha1(f"tcc:{title}|{company}|{country}".encode()).hexdigest()


def cross_source(df: pd.DataFrame) -> pd.DataFrame:
    """Collapse duplicate postings across sources. Keeps the first occurrence."""
    if df.empty:
        return df.copy()
    keys = df.apply(posting_hash, axis=1)
    return df.loc[~keys.duplicated(keep="first")].reset_index(drop=True)
