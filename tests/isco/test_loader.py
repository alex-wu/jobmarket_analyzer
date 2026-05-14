from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from jobpipe.isco.loader import _load, load_isco_labels


def _write_snapshot(path: Path, rows: list[tuple[str, str, str]]) -> Path:
    df = pd.DataFrame(rows, columns=["isco_code", "label", "label_kind"])
    df.to_parquet(path, index=False)
    return path


def test_loads_valid_snapshot(tmp_path: Path) -> None:
    path = _write_snapshot(
        tmp_path / "snap.parquet",
        [("2511", "Systems analysts", "preferred"), ("2511", "data analyst", "alt")],
    )
    df = load_isco_labels(path)
    assert len(df) == 2
    assert set(df.columns) == {"isco_code", "label", "label_kind"}


def test_rejects_missing_columns(tmp_path: Path) -> None:
    path = tmp_path / "snap.parquet"
    pd.DataFrame({"isco_code": ["2511"]}).to_parquet(path, index=False)
    with pytest.raises(ValueError, match="missing required columns"):
        _load(path)


def test_rejects_non_4_digit_codes(tmp_path: Path) -> None:
    path = _write_snapshot(
        tmp_path / "snap.parquet",
        [("251", "too short", "preferred")],
    )
    with pytest.raises(ValueError, match="non-4-digit"):
        _load(path)


def test_default_path_loads_committed_snapshot() -> None:
    df = load_isco_labels()
    assert len(df) > 1000
    assert df["isco_code"].str.match(r"^\d{4}$").all()
    assert (df["isco_code"] == "2511").any()
    assert (df.loc[df["isco_code"] == "2511", "label"] == "Systems analysts").any()


def test_returned_frame_is_a_copy(tmp_path: Path) -> None:
    path = _write_snapshot(
        tmp_path / "snap.parquet",
        [("2511", "Systems analysts", "preferred")],
    )
    a = load_isco_labels(path)
    b = load_isco_labels(path)
    a.loc[0, "label"] = "MUTATED"
    assert b.loc[0, "label"] == "Systems analysts"
