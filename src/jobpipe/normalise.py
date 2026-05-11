"""Pure normalisation step. DataFrames in, DataFrames out. No HTTP, no FS, no DB.

Activated in P2. P0 ships the module skeleton so the import graph is stable and
``mypy --strict`` has a fixed target.
"""

from __future__ import annotations

import pandas as pd


def run(raw: pd.DataFrame) -> pd.DataFrame:
    """Normalise a raw postings DataFrame.

    Pipeline (will be filled in P2):
    1. FX-convert salary fields to EUR via ECB daily rates.
    2. Normalise salary period to annual.
    3. Dedupe by sha1(normalised_url) or sha1(title+company+country).
    4. Tag with ISCO-08 code via rapidfuzz (+ optional LLM fallback).

    For P0 this is a passthrough so the CLI wires up cleanly.
    """
    return raw.copy()
