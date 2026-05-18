"""Load the static ESCO Pillar B (skills) snapshot.

Mirrors `jobpipe.isco.loader`. The parquet is checked into
`config/esco/skills_labels.parquet` (built by
`scripts/build_esco_skills_snapshot.py`) so the pipeline has no runtime
dependency on the live ESCO API or the tabiya mirror.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd

DEFAULT_PATH = Path("config/esco/skills_labels.parquet")
REQUIRED_COLUMNS = (
    "skill_uri",
    "preferred_label",
    "alt_labels",
    "skill_type",
    "reuse_level",
    "related_isco_codes",
)


def _load(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(path)
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            f"ESCO skills snapshot at {path} missing required columns: "
            f"{missing}; got {list(df.columns)}"
        )
    return df.copy()


@lru_cache(maxsize=4)
def _load_cached(path_str: str) -> pd.DataFrame:
    return _load(Path(path_str))


def load_skills(path: Path | None = None) -> pd.DataFrame:
    """Return the ESCO skills snapshot DataFrame.

    Cached per resolved path so repeated calls in one process are free.
    Callers needing isolation (e.g. tests) should pass an explicit `path`.
    """
    resolved = (path or DEFAULT_PATH).resolve()
    return _load_cached(str(resolved)).copy()
