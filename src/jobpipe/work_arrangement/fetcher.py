"""Adzuna ``/v1/api/jobs/{country}/details/{id}`` description fetcher.

The search endpoint truncates posting descriptions to ~500 chars + ellipsis;
the details endpoint returns the full body. Work-arrangement signals (remote
/ hybrid / onsite) frequently appear in the benefits or "About the role"
sections that sit beyond the truncation, so the full body lifts coverage
substantially.

Cost: one HTTP request per posting. At the active preset's ~1000-row
Run-1 volume, the first publish burns ~1000 details calls on top of the
~30 search calls. Subsequent runs only fetch postings that weren't
classified last week (driver in :mod:`jobpipe.runner`), so steady-state
quota drops ~80% by week 4.

Persistence:

- On-disk cache at ``data/cache/work_arrangement/{posting_id}.txt``
  stores the raw description body. Lookups skip HTTP on cache hit.
  Cache lives forever — Adzuna posting bodies are stable post-publish.

- A per-process in-memory dict shadows the disk cache to avoid
  re-reading the same file twice in a single run.

Failure semantics:

- 404 ⇒ posting expired between search and details (Adzuna purges
  closed listings). Returns ``None``; tagger leaves the row NULL.
- Other ``HTTPError`` after retries (3 attempts, exponential backoff)
  propagates as :class:`AdzunaDetailsError`. Caller catches and treats
  as NULL — one bad posting does not fail the run.

Rate limiting: a 0.5s ``time.sleep`` between live HTTP calls spreads
the burst over ~8 minutes for a 1000-row first run, comfortably under
the GitHub Actions workflow ``timeout-minutes: 30`` budget.
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from jobpipe.settings import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://api.adzuna.com/v1/api/jobs"
DEFAULT_CACHE_DIR = Path("data/cache/work_arrangement")
DEFAULT_INTER_CALL_SLEEP_SECONDS = 0.5

# ADR-015: app_id / app_key / api_key sit in the query string on every Adzuna
# request. httpx error messages echo the request URL verbatim — wrapping that
# message into our own RuntimeError bypasses CredentialScrubFilter, which is
# only attached to httpx / httpcore loggers. Scrub before re-raising.
_CREDENTIAL_PARAMS = ("app_id", "app_key", "api_key", "api-key")
_CREDENTIAL_RE = re.compile(
    r"(?i)\b(" + "|".join(re.escape(p) for p in _CREDENTIAL_PARAMS) + r")=[^&\s'\"]+"
)


def _scrub(message: str) -> str:
    return _CREDENTIAL_RE.sub(r"\1=REDACTED", message)


class AdzunaDetailsError(RuntimeError):
    """Non-404 HTTP failure on the details endpoint after retries."""


def _safe_filename(posting_id: str) -> str:
    """Reduce a sha1 hex posting_id to a filesystem-safe name."""
    return "".join(c for c in posting_id if c.isalnum() or c == "_") + ".txt"


class DetailsFetcher:
    """Stateful per-process fetcher with disk cache + in-memory shadow.

    Construction kept cheap: the cache directory is materialised lazily
    on the first write. The ``httpx.Client`` is dependency-injected so
    tests can pass an ``httpx.MockTransport``-backed client.
    """

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        cache_dir: Path | None = None,
        inter_call_sleep: float = DEFAULT_INTER_CALL_SLEEP_SECONDS,
    ) -> None:
        self._own_client = client is None
        self._client = client or httpx.Client(timeout=30.0)
        self._cache_dir = cache_dir or DEFAULT_CACHE_DIR
        self._memory: dict[str, str | None] = {}
        self._inter_call_sleep = inter_call_sleep
        self._calls_made = 0

    @property
    def calls_made(self) -> int:
        """Live HTTP calls issued (cache hits not counted)."""
        return self._calls_made

    def close(self) -> None:
        if self._own_client:
            self._client.close()

    def __enter__(self) -> DetailsFetcher:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def fetch(
        self,
        posting_id: str,
        country: str,
        external_id: str,
    ) -> str | None:
        """Return the full description text for one posting, or ``None``.

        Cache key is ``posting_id`` (the sha1 hash that survives accumulation)
        so the cache stays valid across schema changes that affect
        ``external_id`` shape.
        """
        if posting_id in self._memory:
            return self._memory[posting_id]

        cached = self._read_cache(posting_id)
        if cached is not None:
            self._memory[posting_id] = cached
            return cached

        if not external_id:
            self._memory[posting_id] = None
            return None

        if not settings.adzuna_app_id or not settings.adzuna_app_key:
            raise AdzunaDetailsError(
                "work_arrangement.fetcher: ADZUNA_APP_ID / ADZUNA_APP_KEY missing"
            )

        if self._calls_made > 0 and self._inter_call_sleep > 0:
            time.sleep(self._inter_call_sleep)

        try:
            payload = self._get_details(country, external_id)
        except _NotFound:
            logger.info("work_arrangement.fetcher: posting %s expired upstream (404)", posting_id)
            self._memory[posting_id] = None
            self._write_cache(posting_id, "")
            return None
        except httpx.HTTPError as exc:
            raise AdzunaDetailsError(
                _scrub(f"work_arrangement.fetcher: {country}/{external_id}: {exc}")
            ) from exc
        finally:
            self._calls_made += 1

        body = str(payload.get("description") or "").strip()
        self._memory[posting_id] = body or None
        self._write_cache(posting_id, body)
        return body or None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(httpx.HTTPError),
        reraise=True,
    )
    def _get_details(self, country: str, external_id: str) -> dict[str, Any]:
        url = f"{BASE_URL}/{country.lower()}/details/{external_id}"
        params = {
            "app_id": settings.adzuna_app_id,
            "app_key": settings.adzuna_app_key,
            "content-type": "application/json",
        }
        r = self._client.get(url, params=params)
        if r.status_code == 404:
            raise _NotFound()
        r.raise_for_status()
        return r.json()  # type: ignore[no-any-return]

    def _read_cache(self, posting_id: str) -> str | None:
        path = self._cache_dir / _safe_filename(posting_id)
        if not path.exists():
            return None
        text = path.read_text(encoding="utf-8")
        return text or None

    def _write_cache(self, posting_id: str, body: str) -> None:
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        path = self._cache_dir / _safe_filename(posting_id)
        path.write_text(body, encoding="utf-8")


class _NotFound(httpx.HTTPError):
    """Internal sentinel — 404 is expected and handled, not an error."""

    def __init__(self) -> None:
        super().__init__("404")
