"""Shared HTTP retry policy for source adapters."""

from __future__ import annotations

import httpx


def is_retryable_http_error(exc: BaseException) -> bool:
    """Retry transport failures and 5xx/429 only.

    A 4xx (bad credentials, malformed query, expired resource) is
    deterministic — retrying burns attempts, adds backoff latency, and
    re-logs the credentialed URL each time.
    """
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        return code >= 500 or code == 429
    return isinstance(exc, httpx.TransportError)
