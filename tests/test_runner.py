"""Preset loader + runner tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from jobpipe import sources
from jobpipe.runner import (
    EmptyRunError,
    NoRawRunError,
    PresetError,
    fetch_sources,
    find_latest_raw,
    load_preset,
    run_fetch,
    run_normalise,
    write_raw_parquet,
)
from jobpipe.sources import SourceConfig, SourceFetchError


def _valid_posting_row(idx: int) -> dict[str, object]:
    """A row that satisfies PostingSchema (partial / lazy validation)."""
    now = pd.Timestamp(datetime.now(UTC))
    return {
        "posting_id": f"posting-{idx:04d}",
        "source": "fake",
        "title": f"Data Analyst #{idx}",
        "company": "Test Co",
        "location_raw": "Dublin",
        "country": "IE",
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
        "isco_code": None,
        "isco_match_method": None,
        "isco_match_score": None,
        "raw_payload": "{}",
    }


@pytest.fixture
def fake_source_registered() -> object:
    """Register a tiny FakeAdapter that returns N valid rows."""

    class FakeConfig(SourceConfig):
        n_rows: int = 3

    class _FakeAdapter:
        name = "fake"
        config_model = FakeConfig

        def fetch(self, config: SourceConfig) -> pd.DataFrame:
            cfg = config if isinstance(config, FakeConfig) else FakeConfig(**config.model_dump())
            return pd.DataFrame(_valid_posting_row(i) for i in range(cfg.n_rows))

    instance = _FakeAdapter()
    sources._REGISTRY["fake"] = instance
    yield instance
    sources._REGISTRY.pop("fake", None)


@pytest.fixture
def raising_source_registered() -> object:
    """Register a source that always raises — used to test fail-isolation."""

    class _RaisingAdapter:
        name = "raiser"
        config_model = SourceConfig

        def fetch(self, config: SourceConfig) -> pd.DataFrame:
            raise SourceFetchError("simulated failure")

    instance = _RaisingAdapter()
    sources._REGISTRY["raiser"] = instance
    yield instance
    sources._REGISTRY.pop("raiser", None)


def _write_preset(tmp_path: Path, body: dict[str, object]) -> Path:
    import yaml

    preset = tmp_path / "preset.yaml"
    preset.write_text(yaml.safe_dump(body), encoding="utf-8")
    return preset


def test_load_preset_parses_minimum_fields(tmp_path: Path) -> None:
    body = {"preset_id": "demo", "sources": {"fake": {"enabled": False}}}
    out = load_preset(_write_preset(tmp_path, body))
    assert out["preset_id"] == "demo"
    assert out["sources"]["fake"]["enabled"] is False


def test_load_preset_raises_on_missing_file(tmp_path: Path) -> None:
    with pytest.raises(PresetError, match="not found"):
        load_preset(tmp_path / "missing.yaml")


def test_load_preset_raises_on_invalid_yaml(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("not: valid: yaml: : :", encoding="utf-8")
    with pytest.raises(PresetError):
        load_preset(bad)


def test_load_preset_raises_when_top_level_is_not_a_mapping(tmp_path: Path) -> None:
    bad = tmp_path / "list.yaml"
    bad.write_text("- one\n- two\n", encoding="utf-8")
    with pytest.raises(PresetError, match="mapping"):
        load_preset(bad)


def test_load_preset_requires_preset_id(tmp_path: Path) -> None:
    with pytest.raises(PresetError, match="preset_id"):
        load_preset(_write_preset(tmp_path, {"sources": {}}))


def test_load_preset_requires_sources_mapping(tmp_path: Path) -> None:
    with pytest.raises(PresetError, match="sources"):
        load_preset(_write_preset(tmp_path, {"preset_id": "x"}))


def test_fetch_sources_concatenates_enabled_adapters(fake_source_registered: object) -> None:
    preset = {
        "preset_id": "demo",
        "sources": {"fake": {"enabled": True, "n_rows": 5}},
    }
    df = fetch_sources(preset)
    assert len(df) == 5
    assert (df["source"] == "fake").all()


def test_fetch_sources_skips_disabled(fake_source_registered: object) -> None:
    preset = {
        "preset_id": "demo",
        "sources": {"fake": {"enabled": False, "n_rows": 5}},
    }
    with pytest.raises(EmptyRunError):
        fetch_sources(preset)


def test_fetch_sources_warns_and_skips_unknown_adapter() -> None:
    preset = {
        "preset_id": "demo",
        "sources": {"nope": {"enabled": True}},
    }
    with pytest.raises(EmptyRunError):
        fetch_sources(preset)


def test_fetch_sources_is_fail_isolated(
    fake_source_registered: object,
    raising_source_registered: object,
) -> None:
    """One source raises -> others' rows still land in the output frame."""
    preset = {
        "preset_id": "demo",
        "sources": {
            "raiser": {"enabled": True},
            "fake": {"enabled": True, "n_rows": 2},
        },
    }
    df = fetch_sources(preset)
    assert len(df) == 2
    assert set(df["source"].unique()) == {"fake"}


def test_fetch_sources_raises_empty_when_zero_rows(raising_source_registered: object) -> None:
    preset = {
        "preset_id": "demo",
        "sources": {"raiser": {"enabled": True}},
    }
    with pytest.raises(EmptyRunError):
        fetch_sources(preset)


def test_write_raw_parquet_creates_partition(tmp_path: Path) -> None:
    df = pd.DataFrame([_valid_posting_row(0), _valid_posting_row(1)])
    out = write_raw_parquet(df, "demo", tmp_path)
    assert out.exists()
    assert out.suffix == ".parquet"
    roundtrip = pd.read_parquet(out)
    assert len(roundtrip) == 2


def test_run_fetch_end_to_end(
    fake_source_registered: object,
    tmp_path: Path,
) -> None:
    preset_path = _write_preset(
        tmp_path,
        {
            "preset_id": "demo",
            "sources": {"fake": {"enabled": True, "n_rows": 4}},
        },
    )
    out = run_fetch(preset_path, out_root=tmp_path / "data")
    assert out.exists()
    df = pd.read_parquet(out)
    assert len(df) == 4


def test_find_latest_raw_returns_most_recent_bundle(tmp_path: Path) -> None:
    raw_root = tmp_path / "raw"
    older = raw_root / "demo__20260101T000000Z-aaaaaaaa"
    newer = raw_root / "demo__20260601T000000Z-bbbbbbbb"
    older.mkdir(parents=True)
    newer.mkdir(parents=True)
    pd.DataFrame([_valid_posting_row(0)]).to_parquet(older / "postings_raw.parquet", index=False)
    pd.DataFrame([_valid_posting_row(1)]).to_parquet(newer / "postings_raw.parquet", index=False)

    # Force mtime so the test isn't flaky on fast filesystems.
    import os

    older_ts = datetime(2026, 1, 1, tzinfo=UTC).timestamp()
    newer_ts = datetime(2026, 6, 1, tzinfo=UTC).timestamp()
    os.utime(older, (older_ts, older_ts))
    os.utime(newer, (newer_ts, newer_ts))

    out = find_latest_raw("demo", tmp_path)
    assert out == newer / "postings_raw.parquet"


def test_find_latest_raw_raises_when_no_bundle(tmp_path: Path) -> None:
    (tmp_path / "raw").mkdir()
    with pytest.raises(NoRawRunError, match="demo"):
        find_latest_raw("demo", tmp_path)


def test_run_normalise_end_to_end(
    fake_source_registered: object,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Stub ECB fetch — no live HTTP in unit tests.
    monkeypatch.setattr(
        "jobpipe.runner.fx.load_rates", lambda: {"EUR": 1.0, "GBP": 0.85, "USD": 1.10}
    )

    preset_path = _write_preset(
        tmp_path,
        {
            "preset_id": "demo",
            "sources": {"fake": {"enabled": True, "n_rows": 3}},
        },
    )
    raw_out = run_fetch(preset_path, out_root=tmp_path / "data")
    assert raw_out.exists()

    enriched_out = run_normalise(preset_path, out_root=tmp_path / "data")
    assert enriched_out.exists()
    assert enriched_out.parent.parent.name == "enriched"
    # Same run_id directory as the raw bundle.
    assert enriched_out.parent.name == raw_out.parent.name

    df = pd.read_parquet(enriched_out)
    # Fake rows are country=IE → EUR rate=1, salary stays 50k/60k.
    assert len(df) == 3
    assert df["salary_min_eur"].iloc[0] == pytest.approx(50_000.0)
