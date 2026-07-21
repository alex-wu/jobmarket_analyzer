"""Credential redaction shared across the pipeline (ADR-015).

Adzuna (and likely future free-tier sources) pass credentials as URL query
params. httpx error messages echo the full request URL verbatim, so any code
path that logs an httpx exception — directly, wrapped, or as a chained
traceback — must scrub before the text reaches a handler.
"""

from __future__ import annotations

import re

# Matched case-insensitively; both underscore and hyphen forms covered.
_CREDENTIAL_PARAMS = ("app_id", "app_key", "api_key", "api-key")
CREDENTIAL_RE = re.compile(
    r"(?i)\b(" + "|".join(re.escape(p) for p in _CREDENTIAL_PARAMS) + r")=[^&\s'\"]+"
)


def scrub_credentials(message: str) -> str:
    """Replace credential query-param values in ``message`` with ``REDACTED``."""
    return CREDENTIAL_RE.sub(r"\1=REDACTED", message)
