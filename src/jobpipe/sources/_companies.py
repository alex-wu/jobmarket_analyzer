"""Shared helpers for ATS + remote-jobs source adapters.

Two responsibilities:

1. :func:`load_companies_file` — read ``config/companies/*.yaml`` and return the
   slug list for one ATS key. The same companies file is shared across the
   Greenhouse / Lever / Ashby / Personio adapters.
2. :func:`match_country` — turn a free-text location string ("Dublin, Ireland",
   "Remote (Europe)") into an ISO-3166 alpha-2 code plus a ``is_remote`` flag,
   honouring the preset's allowed-countries list (including ``remote-europe``
   and ``remote-worldwide`` pseudo-codes).

Both helpers are deliberately data-driven so adapters stay thin.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from jobpipe.sources import SourceFetchError

COUNTRY_ALIASES: dict[str, tuple[str, ...]] = {
    "ie": ("ireland", "dublin", "cork", "galway", "limerick", "waterford"),
    "gb": (
        "united kingdom",
        "uk",
        "england",
        "scotland",
        "wales",
        "london",
        "manchester",
        "edinburgh",
        "glasgow",
        "birmingham",
        "leeds",
    ),
    "de": (
        "germany",
        "deutschland",
        "berlin",
        "munich",
        "münchen",
        "hamburg",
        "frankfurt",
        "cologne",
        "köln",
        "stuttgart",
    ),
    "fr": ("france", "paris", "lyon", "marseille", "toulouse"),
    "nl": ("netherlands", "nederland", "amsterdam", "rotterdam", "utrecht", "eindhoven"),
    "es": ("spain", "españa", "madrid", "barcelona", "valencia", "sevilla", "seville"),
    "it": ("italy", "italia", "rome", "roma", "milan", "milano", "turin", "torino"),
    "be": ("belgium", "brussels", "bruxelles", "antwerp", "antwerpen"),
    "at": ("austria", "vienna", "wien"),
    "pt": ("portugal", "lisbon", "lisboa", "porto"),
    "fi": ("finland", "helsinki"),
    "se": ("sweden", "stockholm", "gothenburg"),
    "dk": ("denmark", "copenhagen"),
}

REMOTE_PATTERNS: dict[str, tuple[str, ...]] = {
    "remote-europe": (
        "remote (europe)",
        "remote europe",
        "remote, europe",
        "remote - europe",
        "europe",
        "emea",
    ),
    "remote-worldwide": ("remote", "worldwide", "anywhere"),
}


def load_companies_file(path: Path, ats_key: str) -> list[str]:
    """Read ``path`` and return the slug list for ``ats_key``.

    Returns an empty list if the key is absent or its value is an empty list.
    Raises :class:`SourceFetchError` on missing file, invalid YAML, or
    non-list value for the requested key.
    """
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SourceFetchError(f"companies file not found: {path}") from exc
    except yaml.YAMLError as exc:
        raise SourceFetchError(f"companies file {path} is not valid YAML: {exc}") from exc

    if not isinstance(raw, dict):
        raise SourceFetchError(f"companies file {path} must be a YAML mapping")

    slugs = raw.get(ats_key)
    if slugs is None:
        return []
    if not isinstance(slugs, list):
        raise SourceFetchError(
            f"companies file {path}: {ats_key!r} must be a list, got {type(slugs).__name__}"
        )
    return [str(s).strip() for s in slugs if s]


def match_country(
    location_text: str | None,
    allowed_codes: list[str],
) -> tuple[str | None, bool]:
    """Match a free-text location against an allowed-codes list.

    ``allowed_codes`` may mix real ISO-3166 alpha-2 codes (``"ie"``, ``"de"``)
    with pseudo-codes (``"remote-europe"``, ``"remote-worldwide"``). A real-code
    hit beats a remote-pseudo hit — "Dublin, Remote" with ``["ie","remote-europe"]``
    returns ``("IE", False)``, not ``("IE", True)``.

    Returns the tuple ``(iso2_uppercase | None, is_remote)``. PostingSchema's
    strict 2-char country constraint means remote-only rows are only accepted
    when at least one real ISO-2 code sits in ``allowed_codes`` to anchor them.
    """
    if not location_text:
        return None, False
    haystack = location_text.lower()

    for code in allowed_codes:
        aliases = COUNTRY_ALIASES.get(code.lower())
        if aliases is None:
            continue
        if any(alias in haystack for alias in aliases):
            return code.upper(), False

    real_codes = [c for c in allowed_codes if c.lower() in COUNTRY_ALIASES]
    for pseudo in allowed_codes:
        patterns = REMOTE_PATTERNS.get(pseudo.lower())
        if patterns is None:
            continue
        if any(p in haystack for p in patterns):
            if real_codes:
                return real_codes[0].upper(), True
            return None, True

    return None, False
