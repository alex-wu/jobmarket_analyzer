"""Tests for ``jobpipe.duckdb_io.export_partitioned``."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from jobpipe import __version__
from jobpipe.duckdb_io import MANIFEST_SCHEMA_VERSION, PublishError, export_partitioned


def _posting_row(
    idx: int,
    *,
    country: str = "IE",
    posted_at: datetime | None = None,
    source: str = "fake",
    isco_match_method: str | None = "fuzzy",
) -> dict[str, object]:
    now = pd.Timestamp(posted_at or datetime.now(UTC))
    return {
        "posting_id": f"posting-{idx:04d}",
        "source": source,
        "title": f"Data Analyst #{idx}",
        "company": "Test Co",
        "location_raw": "Dublin",
        "country": country,
        "region": None,
        "remote": None,
        "salary_min_eur": 50_000.0,
        "salary_max_eur": 60_000.0,
        "salary_period": "annual",
        "salary_annual_eur_p50": 55_000.0,
        "salary_imputed": False,
        "posted_at": now,
        "ingested_at": now,
        "posting_url": f"https://example.test/jobs/{idx}",
        "isco_code": "2511" if isco_match_method else None,
        "isco_match_method": isco_match_method,
        "isco_match_score": 0.9 if isco_match_method else None,
        "raw_payload": "{}",
    }


def _benchmark_row(isco_code: str, country: str) -> dict[str, object]:
    return {
        "isco_code": isco_code,
        "country": country,
        "period": "2024",
        "currency": "EUR",
        "median_eur": 55_000.0,
        "p25_eur": None,
        "p75_eur": None,
        "n_observations": pd.NA,
        "source": "cso",
        "source_url": "http://example.test/bench",
        "retrieved_at": pd.Timestamp(datetime.now(UTC)),
    }


def _write_postings(path: Path, rows: list[dict[str, object]]) -> Path:
    df = pd.DataFrame(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    return path


def test_export_partitioned_round_trips_rows(tmp_path: Path) -> None:
    src = _write_postings(
        tmp_path / "enriched" / "postings.parquet",
        [_posting_row(i) for i in range(5)],
    )
    out = export_partitioned(
        src,
        None,
        tmp_path / "publish",
        partition_by=["country", "year_month"],
        preset_id="demo",
        run_id="demo__20260515T060000Z-abcd1234",
    )
    assert out == tmp_path / "publish"

    rows = duckdb.sql(
        f"SELECT count(*) FROM '{(tmp_path / 'publish' / 'postings').as_posix()}/**/*.parquet'"
    ).fetchone()
    assert rows is not None
    assert rows[0] == 5


def test_export_partitioned_emits_hive_layout(tmp_path: Path) -> None:
    src = _write_postings(
        tmp_path / "enriched" / "postings.parquet",
        [
            _posting_row(0, country="IE", posted_at=datetime(2026, 5, 1, tzinfo=UTC)),
            _posting_row(1, country="GB", posted_at=datetime(2026, 5, 2, tzinfo=UTC)),
            _posting_row(2, country="GB", posted_at=datetime(2026, 6, 3, tzinfo=UTC)),
        ],
    )
    export_partitioned(
        src,
        None,
        tmp_path / "publish",
        partition_by=["country", "year_month"],
        preset_id="demo",
        run_id="run-1",
    )

    postings_root = tmp_path / "publish" / "postings"
    found = {p.relative_to(postings_root).as_posix() for p in postings_root.rglob("*.parquet")}
    # At least one parquet under each expected partition prefix.
    assert any(p.startswith("country=IE/year_month=2026-05/") for p in found)
    assert any(p.startswith("country=GB/year_month=2026-05/") for p in found)
    assert any(p.startswith("country=GB/year_month=2026-06/") for p in found)


def test_export_partitioned_writes_manifest_with_expected_keys(tmp_path: Path) -> None:
    src = _write_postings(
        tmp_path / "enriched" / "postings.parquet",
        [
            _posting_row(0, country="IE", source="greenhouse", isco_match_method="fuzzy"),
            _posting_row(1, country="IE", source="adzuna", isco_match_method="fuzzy"),
            _posting_row(2, country="GB", source="adzuna", isco_match_method="none"),
        ],
    )
    export_partitioned(
        src,
        None,
        tmp_path / "publish",
        partition_by=["country", "year_month"],
        preset_id="data_analyst_ireland",
        run_id="data_analyst_ireland__20260515T060000Z-abcd1234",
        git_sha="deadbeef" * 5,
    )

    manifest = json.loads((tmp_path / "publish" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == MANIFEST_SCHEMA_VERSION
    assert manifest["preset_id"] == "data_analyst_ireland"
    assert manifest["run_id"] == "data_analyst_ireland__20260515T060000Z-abcd1234"
    assert manifest["pipeline_version"] == __version__
    assert manifest["git_sha"] == "deadbeef" * 5
    assert manifest["partition_by"] == ["country", "year_month"]
    assert manifest["postings"]["row_count"] == 3
    assert manifest["postings"]["source_counts"] == {"adzuna": 2, "greenhouse": 1}
    assert manifest["postings"]["country_counts"] == {"IE": 2, "GB": 1}
    assert manifest["postings"]["isco_match_method_counts"] == {"fuzzy": 2, "none": 1}
    assert "benchmarks" not in manifest  # none supplied


def test_export_partitioned_copies_benchmarks_when_present(tmp_path: Path) -> None:
    src = _write_postings(
        tmp_path / "enriched" / "postings.parquet",
        [_posting_row(0, country="IE")],
    )
    bench_src = tmp_path / "enriched" / "benchmarks.parquet"
    pd.DataFrame(
        [_benchmark_row("2511", "IE"), _benchmark_row("2521", "DE")],
    ).to_parquet(bench_src, index=False)

    export_partitioned(
        src,
        bench_src,
        tmp_path / "publish",
        partition_by=["country", "year_month"],
        preset_id="demo",
        run_id="run-1",
    )

    bench_out = tmp_path / "publish" / "benchmarks.parquet"
    assert bench_out.exists()
    roundtrip = pd.read_parquet(bench_out)
    assert len(roundtrip) == 2

    manifest = json.loads((tmp_path / "publish" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["benchmarks"]["row_count"] == 2
    assert manifest["benchmarks"]["source_counts"] == {"cso": 2}
    assert manifest["benchmarks"]["country_counts"] == {"IE": 1, "DE": 1}


def test_export_partitioned_omits_benchmarks_block_when_path_missing(tmp_path: Path) -> None:
    src = _write_postings(
        tmp_path / "enriched" / "postings.parquet",
        [_posting_row(0)],
    )
    export_partitioned(
        src,
        tmp_path / "enriched" / "nonexistent.parquet",
        tmp_path / "publish",
        partition_by=["country", "year_month"],
        preset_id="demo",
        run_id="run-1",
    )
    manifest = json.loads((tmp_path / "publish" / "manifest.json").read_text(encoding="utf-8"))
    assert "benchmarks" not in manifest
    assert not (tmp_path / "publish" / "benchmarks.parquet").exists()


def test_export_partitioned_raises_when_postings_missing(tmp_path: Path) -> None:
    with pytest.raises(PublishError, match="not found"):
        export_partitioned(
            tmp_path / "missing.parquet",
            None,
            tmp_path / "publish",
            partition_by=["country", "year_month"],
            preset_id="demo",
            run_id="run-1",
        )


def test_export_partitioned_raises_when_postings_empty(tmp_path: Path) -> None:
    empty = tmp_path / "enriched" / "postings.parquet"
    empty.parent.mkdir(parents=True)
    pd.DataFrame(columns=list(_posting_row(0))).to_parquet(empty, index=False)
    with pytest.raises(PublishError, match="empty"):
        export_partitioned(
            empty,
            None,
            tmp_path / "publish",
            partition_by=["country", "year_month"],
            preset_id="demo",
            run_id="run-1",
        )


def test_export_partitioned_raises_on_unknown_partition_column(tmp_path: Path) -> None:
    src = _write_postings(
        tmp_path / "enriched" / "postings.parquet",
        [_posting_row(0)],
    )
    with pytest.raises(PublishError, match="unknown columns"):
        export_partitioned(
            src,
            None,
            tmp_path / "publish",
            partition_by=["country", "no_such_column"],
            preset_id="demo",
            run_id="run-1",
        )
