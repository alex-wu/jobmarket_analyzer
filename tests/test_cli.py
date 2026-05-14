"""CLI surface tests via Typer's ``CliRunner``.

These tests exercise the exit codes + path-echo contract of the three
``jobpipe`` commands. Adapter logic is unit-tested elsewhere; here we just
confirm that the Typer wiring routes errors to red-stderr + exit 2 and
prints the resulting path on success.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest
import yaml
from typer.testing import CliRunner

from jobpipe import sources
from jobpipe.cli import app
from jobpipe.sources import SourceConfig

runner = CliRunner()


def _valid_posting_row(idx: int) -> dict[str, object]:
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
def fake_source() -> object:
    """Tiny registered FakeAdapter so the CLI commands have data to process."""

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


def _write_preset(tmp_path: Path, body: dict[str, object]) -> Path:
    preset = tmp_path / "preset.yaml"
    preset.write_text(yaml.safe_dump(body), encoding="utf-8")
    return preset


def test_cli_fetch_succeeds_and_echoes_path(tmp_path: Path, fake_source: object) -> None:
    preset = _write_preset(
        tmp_path,
        {"preset_id": "demo", "sources": {"fake": {"enabled": True, "n_rows": 2}}},
    )
    result = runner.invoke(
        app,
        ["fetch", "--preset", str(preset), "--out-root", str(tmp_path / "data")],
    )
    assert result.exit_code == 0, result.stderr
    out_path = Path(result.stdout.strip())
    assert out_path.exists()
    assert out_path.suffix == ".parquet"


def test_cli_fetch_returns_2_on_missing_preset(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["fetch", "--preset", str(tmp_path / "missing.yaml"), "--out-root", str(tmp_path / "data")],
    )
    assert result.exit_code == 2
    assert "preset error" in result.stderr


def test_cli_normalise_returns_2_when_no_raw_bundle(tmp_path: Path) -> None:
    preset = _write_preset(
        tmp_path,
        {"preset_id": "demo", "sources": {"fake": {"enabled": False}}},
    )
    result = runner.invoke(
        app,
        ["normalise", "--preset", str(preset), "--out-root", str(tmp_path / "data")],
    )
    assert result.exit_code == 2
    assert "normalise failed" in result.stderr


def test_cli_publish_end_to_end(
    tmp_path: Path,
    fake_source: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("jobpipe.runner.fx.load_rates", lambda: {"EUR": 1.0, "GBP": 0.85})
    preset = _write_preset(
        tmp_path,
        {
            "preset_id": "demo",
            "sources": {"fake": {"enabled": True, "n_rows": 2}},
            "publish": {"partition_by": ["country", "year_month"]},
        },
    )
    data_root = tmp_path / "data"

    assert (
        runner.invoke(
            app, ["fetch", "--preset", str(preset), "--out-root", str(data_root)]
        ).exit_code
        == 0
    )
    assert (
        runner.invoke(
            app, ["normalise", "--preset", str(preset), "--out-root", str(data_root)]
        ).exit_code
        == 0
    )

    result = runner.invoke(
        app,
        ["publish", "--preset", str(preset), "--out-root", str(data_root)],
    )
    assert result.exit_code == 0, result.stderr
    bundle = Path(result.stdout.strip())
    assert bundle.exists()
    assert (bundle / "manifest.json").exists()
    assert (bundle / "postings").is_dir()


def test_cli_publish_returns_2_when_no_enriched_bundle(tmp_path: Path) -> None:
    preset = _write_preset(
        tmp_path,
        {
            "preset_id": "demo",
            "sources": {"fake": {"enabled": False}},
            "publish": {"partition_by": ["country", "year_month"]},
        },
    )
    result = runner.invoke(
        app,
        ["publish", "--preset", str(preset), "--out-root", str(tmp_path / "data")],
    )
    assert result.exit_code == 2
    assert "publish failed" in result.stderr


def test_cli_publish_returns_2_when_publish_block_missing(tmp_path: Path) -> None:
    preset = _write_preset(
        tmp_path,
        {"preset_id": "demo", "sources": {"fake": {"enabled": False}}},
    )
    result = runner.invoke(
        app,
        ["publish", "--preset", str(preset), "--out-root", str(tmp_path / "data")],
    )
    assert result.exit_code == 2
    assert "preset error" in result.stderr
