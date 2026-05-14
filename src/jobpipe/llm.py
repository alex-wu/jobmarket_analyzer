"""Optional LLM client interface — stub for v1; do not import in production code.

Per DECISIONS.md ADR-013, HN Algolia + the real LLM client are descoped from
v1. This module persists only to lock the calling contract so a future PR can
drop in the real client without rippling through callers. ADR-007 keeps the
pipeline materialising end-to-end with ``LLM_ENABLED=false`` as the default,
which is also v1's permanent CI configuration.

Future use cases (post-v1):
* ``classify_title_to_isco`` — fill ``isco_match_method="llm"`` rows where
  rapidfuzz scored below ADR-006's 0.88 cutoff.
* "Who is hiring?" HN Algolia comment extraction (separate source adapter).
"""

from __future__ import annotations

from jobpipe.settings import settings


class LLMUnavailableError(RuntimeError):
    """Raised when an LLM call is attempted with ``LLM_ENABLED=false``.

    Callers should catch this and fall through to the deterministic path.
    """


def classify_title_to_isco(
    title: str,
    allowed_codes: list[str],
) -> tuple[str, float] | None:
    """Map a free-text job title to one of ``allowed_codes`` via the LLM.

    Returns ``(isco_code, confidence)`` where ``confidence`` ∈ [0, 1], or
    ``None`` when the LLM declines to commit (e.g. ambiguous title).

    Raises :class:`LLMUnavailableError` when ``LLM_ENABLED=false``.
    Raises :class:`NotImplementedError` until the follow-up PR ships the
    OpenAI-compatible client — the stub guards the contract.
    """
    if not settings.llm_enabled:
        raise LLMUnavailableError(
            "LLM disabled; set LLM_ENABLED=true and provide "
            "LLM_BASE_URL / LLM_API_KEY / LLM_MODEL to enable."
        )
    raise NotImplementedError(
        "LLM ISCO classifier lands in the follow-up PR; "
        f"deterministic fuzzy match handles {len(allowed_codes)} candidate codes for {title!r}."
    )
