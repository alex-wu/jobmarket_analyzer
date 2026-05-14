"""Load the static ESCO ISCO-08 label snapshot.

The parquet is checked into ``config/esco/isco08_labels.parquet`` so the pipeline
has no runtime dependency on the live ESCO API. See ``config/esco/README.md``
for provenance + refresh instructions.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd

DEFAULT_PATH = Path("config/esco/isco08_labels.parquet")
REQUIRED_COLUMNS = ("isco_code", "label", "label_kind")


def _load(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(path)
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"ESCO snapshot at {path} missing required columns: {missing}; got {list(df.columns)}"
        )
    bad = df.loc[~df["isco_code"].astype(str).str.match(r"^\d{4}$")]
    if not bad.empty:
        raise ValueError(
            f"ESCO snapshot at {path} contains non-4-digit ISCO codes: {bad['isco_code'].head().tolist()}"
        )
    return df.copy()


@lru_cache(maxsize=4)
def _load_cached(path_str: str) -> pd.DataFrame:
    return _load(Path(path_str))


def load_isco_labels(path: Path | None = None) -> pd.DataFrame:
    """Return the ESCO label snapshot DataFrame.

    Cached per resolved path so repeated calls in one process are free.
    Callers needing isolation (e.g. tests) should pass an explicit ``path``.
    """
    resolved = (path or DEFAULT_PATH).resolve()
    return _load_cached(str(resolved)).copy()
