"""Multilingual keyword patterns for work-arrangement inference.

`\\b`-anchored regex (not Aho-Corasick) — at ~30 phrases per language a
compiled alternation is faster to author and just as fast at runtime.

Each dict is keyed by ISO-639 language code. The tagger combines the
country's primary language with `en` (English) — Spanish/German/French
postings frequently embed "remote" / "hybrid" verbatim in English.
"""

from __future__ import annotations

import re

HYBRID_PATTERNS: dict[str, list[str]] = {
    "en": [
        r"\bhybrid\b",
        r"\bhybrid\s+work\b",
        r"\bhybrid\s+model\b",
        r"\bhybrid\s+role\b",
        r"\b\d+\s+days?\s+(in|at)\s+(the\s+)?office\b",
        r"\b\d+\s+days?\s+(in|at)\s+home\b",
        r"\bpart\s+remote\b",
    ],
    "es": [
        r"\bh[ií]brido\b",
        r"\bh[ií]brida\b",
        r"\bmodalidad\s+h[ií]brida\b",
        r"\btrabajo\s+h[ií]brido\b",
        r"\bformato\s+h[ií]brido\b",
    ],
    "de": [
        r"\bhybrid\b",
        r"\bhybrides?\s+arbeit\b",
        r"\bteilweise\s+remote\b",
    ],
    "fr": [
        r"\bhybride\b",
        r"\btravail\s+hybride\b",
    ],
    "it": [
        r"\bibrido\b",
        r"\blavoro\s+ibrido\b",
    ],
}

REMOTE_PATTERNS: dict[str, list[str]] = {
    "en": [
        r"\b(?:fully|100%|completely|entirely)\s+remote\b",
        r"\bremote[\s\-]?first\b",
        r"\bremote\s+(?:role|position|opportunity|work|job|working)\b",
        r"\bwork[\s\-]+from[\s\-]+home\b",
        r"\bwork\s+from\s+anywhere\b",
        r"\bWFH\b",
        r"\bfully\s+distributed\b",
        r"\b100%\s+work\s+from\s+home\b",
        # Standalone "remote" in delimited contexts: titles like
        # "Data Analyst (Remote)", "Engineer | Remote", "Lead — Remote".
        # Avoids matching geographic "remote area / village / location".
        r"(?:[\(\|\-–—]\s*)remote\b",
        r"\bremote\s*(?:[\)\|])",
    ],
    "es": [
        r"\b(?:totalmente|completamente|100%)\s+remoto\b",
        r"\bteletrabajo\b",
        r"\btrabajo\s+a\s+distancia\b",
        r"\btrabajo\s+remoto\b",
        r"\bdesde\s+casa\b",
        r"\bremoto\s+100%\b",
    ],
    "de": [
        r"\b(?:voll(?:st[äa]ndig)?|100%)\s+remote\b",
        r"\bhomeoffice\b",
        r"\bheimarbeit\b",
        r"\bfernarbeit\b",
    ],
    "fr": [
        r"\bt[ée]l[ée]travail\s+(?:complet|total|100%)\b",
        r"\b100\s*%\s+t[ée]l[ée]travail\b",
        r"\bt[ée]l[ée]travail\b",
        r"\b(?:travail\s+)?(?:[àa]\s+)?distanciel\b",
        r"\bdistance(?:l|ll)?\b",
    ],
    "it": [
        r"\bremoto\b",
        r"\bsmart\s+working\b",
        r"\blavoro\s+da\s+casa\b",
        r"\blavoro\s+da\s+remoto\b",
    ],
}

ONSITE_PATTERNS: dict[str, list[str]] = {
    "en": [
        r"\bon[\s\-]?site\b",
        r"\bin[\s\-]+office\b",
        r"\bin[\s\-]+person\b",
        r"\bno\s+remote\b",
        r"\boffice[\s\-]+based\b",
        r"\bfully\s+on[\s\-]?site\b",
    ],
    "es": [
        r"\bpresencial\b",
        r"\ben\s+oficina\b",
        r"\btrabajo\s+presencial\b",
        r"\bmodalidad\s+presencial\b",
    ],
    "de": [
        r"\bvor\s+ort\b",
        r"\bpr[äa]senz\b",
        r"\bim\s+b[üu]ro\b",
    ],
    "fr": [
        r"\bsur\s+site\b",
        r"\bpr[ée]sentiel\b",
        r"\bau\s+bureau\b",
    ],
    "it": [
        r"\bin\s+sede\b",
        r"\bin\s+presenza\b",
        r"\bin\s+ufficio\b",
    ],
}


# Country ISO-2 → languages to scan, in addition to English.
# English is always combined unless already present (multilingual postings
# in EU markets frequently embed English work-arrangement keywords verbatim).
COUNTRY_LANGUAGES: dict[str, tuple[str, ...]] = {
    "gb": ("en",),
    "us": ("en",),
    "ie": ("en",),
    "au": ("en",),
    "nz": ("en",),
    "ca": ("en",),
    "za": ("en",),
    "in": ("en",),
    "sg": ("en",),
    "es": ("es", "en"),
    "mx": ("es", "en"),
    "de": ("de", "en"),
    "at": ("de", "en"),
    "ch": ("de", "fr", "it", "en"),
    "fr": ("fr", "en"),
    "be": ("fr", "en"),
    "lu": ("fr", "de", "en"),
    "it": ("it", "en"),
    "nl": ("en",),
    "pl": ("en",),
    "br": ("en",),
}

DEFAULT_LANGUAGES: tuple[str, ...] = ("en",)


def _compile(patterns_by_lang: dict[str, list[str]]) -> dict[str, list[re.Pattern[str]]]:
    return {
        lang: [re.compile(p, re.IGNORECASE) for p in patterns]
        for lang, patterns in patterns_by_lang.items()
    }


HYBRID = _compile(HYBRID_PATTERNS)
REMOTE = _compile(REMOTE_PATTERNS)
ONSITE = _compile(ONSITE_PATTERNS)


def languages_for_country(country: str | None) -> tuple[str, ...]:
    if country is None:
        return DEFAULT_LANGUAGES
    return COUNTRY_LANGUAGES.get(country.lower(), DEFAULT_LANGUAGES)
