"""Skills snapshot loader — parquet round-trip + schema guard."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from jobpipe.skills.loader import REQUIRED_COLUMNS, load_skills


def _write(path: Path, df: pd.DataFrame) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    return path


def test_load_skills_round_trip(tmp_path: Path) -> None:
    src = pd.DataFrame(
        [
            {
                "skill_uri": "http://example.test/skill/1",
                "preferred_label": "SQL",
                "alt_labels": ["sequel"],
                "skill_type": "skill/competence",
                "reuse_level": "cross-sector",
                "related_isco_codes": ["2521"],
            }
        ]
    )
    path = _write(tmp_path / "skills.parquet", src)
    out = load_skills(path)
    assert list(out.columns) == list(REQUIRED_COLUMNS)
    assert out.loc[0, "preferred_label"] == "SQL"
    assert list(out.loc[0, "alt_labels"]) == ["sequel"]
    assert list(out.loc[0, "related_isco_codes"]) == ["2521"]


def test_load_skills_rejects_missing_columns(tmp_path: Path) -> None:
    src = pd.DataFrame([{"skill_uri": "x", "preferred_label": "x"}])
    path = _write(tmp_path / "bad.parquet", src)
    with pytest.raises(ValueError, match="missing required columns"):
        load_skills(path)
