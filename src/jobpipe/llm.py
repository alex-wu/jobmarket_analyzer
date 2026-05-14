"""Optional LLM client interface — stub for P4, real implementation in a follow-up.

Per DECISIONS.md ADR-007, the pipeline must materialise end-to-end with
``LLM_ENABLED=false`` (default). The CI cron leaves LLM off; local runs that
opt in (and accept the API cost) get the gap-filling pass on top of the
deterministic rapidfuzz path.

This module exists in P4 only to nail the calling contract so the follow-up
PR drops in the real client without rippling through callers. Nothing in
the current pipeline imports the public functions yet.

Future use cases:
* ``classify_title_to_isco`` — fill ``isco_match_method="llm"`` rows where
  rapidfuzz scored below ADR-006's 0.88 cutoff.
* "Who is hiring?" HN Algolia comment extraction (separate adapter).
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
