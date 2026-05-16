"""Tests for the post-publish manifest gate (``jobpipe gate``)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from jobpipe.cli import app
from jobpipe.gate import GateError, check_manifest, run_gate

runner = CliRunner()


def _manifest(
    *,
    total: int = 150,
    source_counts: dict[str, int] | None = None,
    benchmarks: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a minimal manifest shaped like ``duckdb_io._postings_stats``."""
    base: dict[str, Any] = {
        "schema_version": "1",
        "preset_id": "data_analyst_ireland",
        "run_id": "data_analyst_ireland__20260515T060000Z-abc12345",
        "postings": {
            "row_count": total,
            "source_counts": source_counts
            if source_counts is not None
            else {"adzuna": 50, "greenhouse": 30, "lever": 25, "ashby": 25, "personio": 20},
            "country_counts": {"IE": total},
            "isco_match_method_counts": {"fuzzy": total},
        },
    }
    if benchmarks is not None:
        base["benchmarks"] = benchmarks
    return base


def _preset(
    *,
    sources: dict[str, dict[str, Any]] | None = None,
    benchmarks: dict[str, dict[str, Any]] | None = None,
    gate_block: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "preset_id": "data_analyst_ireland",
        "sources": sources
        if sources is not None
        else {
            "adzuna": {"enabled": True},
            "greenhouse": {"enabled": True},
            "lever": {"enabled": True},
            "ashby": {"enabled": True},
            "personio": {"enabled": True},
        },
    }
    if benchmarks is not None:
        base["benchmarks"] = benchmarks
    if gate_block is not None:
        base["gate"] = gate_block
    return base


def test_healthy_run_passes() -> None:
    issues = check_manifest(
        _manifest(),
        _preset(),
        min_total_rows=20,
        allow_zero_sources=set(),
    )
    assert issues == []


def test_below_threshold_total_fails() -> None:
    issues = check_manifest(
        _manifest(total=5, source_counts={"adzuna": 5}),
        _preset(sources={"adzuna": {"enabled": True}}),
        min_total_rows=20,
        allow_zero_sources=set(),
    )
    assert any("below threshold 20" in msg for msg in issues)


def test_one_declared_source_missing() -> None:
    counts = {"adzuna": 50, "greenhouse": 30, "ashby": 25, "personio": 20}  # no lever
    issues = check_manifest(
        _manifest(source_counts=counts, total=sum(counts.values())),
        _preset(),
        min_total_rows=20,
        allow_zero_sources=set(),
    )
    assert any("source lever" in msg for msg in issues)
    assert len([m for m in issues if "zero rows" in m]) == 1


def test_multiple_declared_sources_missing() -> None:
    counts = {"adzuna": 200}  # only adzuna healthy
    issues = check_manifest(
        _manifest(source_counts=counts, total=200),
        _preset(),
        min_total_rows=20,
        allow_zero_sources=set(),
    )
    missing = {m for m in issues if "zero rows" in m}
    assert len(missing) == 4  # greenhouse, lever, ashby, personio


def test_disabled_source_missing_is_fine() -> None:
    issues = check_manifest(
        _manifest(source_counts={"adzuna": 200}, total=200),
        _preset(sources={"adzuna": {"enabled": True}, "oecd": {"enabled": False}}),
        min_total_rows=20,
        allow_zero_sources=set(),
    )
    assert issues == []


def test_allow_zero_sources_whitelists_enabled_missing() -> None:
    counts = {"adzuna": 200}  # lever absent
    issues = check_manifest(
        _manifest(source_counts=counts, total=200),
        _preset(
            sources={"adzuna": {"enabled": True}, "lever": {"enabled": True}},
        ),
        min_total_rows=20,
        allow_zero_sources={"lever"},
    )
    assert issues == []


def test_missing_postings_block_fails() -> None:
    issues = check_manifest(
        {"schema_version": "1"},
        _preset(),
        min_total_rows=20,
        allow_zero_sources=set(),
    )
    assert any("no 'postings' block" in msg for msg in issues)


def test_benchmarks_block_enforces_enabled_coverage() -> None:
    manifest = _manifest(
        benchmarks={"row_count": 5, "source_counts": {"cso": 5}},  # missing eurostat
    )
    preset = _preset(
        benchmarks={"cso": {"enabled": True}, "eurostat": {"enabled": True}},
    )
    issues = check_manifest(
        manifest,
        preset,
        min_total_rows=20,
        allow_zero_sources=set(),
    )
    assert any("benchmark eurostat" in msg for msg in issues)


def test_no_benchmarks_block_in_manifest_is_silent() -> None:
    # Zero-benchmark run is not fatal per runner.py invariant.
    preset = _preset(benchmarks={"cso": {"enabled": True}})
    issues = check_manifest(
        _manifest(),
        preset,
        min_total_rows=20,
        allow_zero_sources=set(),
    )
    assert issues == []


def test_run_gate_reads_min_total_from_preset(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    preset_path = tmp_path / "preset.yaml"
    manifest_path.write_text(
        json.dumps(_manifest(total=15, source_counts={"adzuna": 15})),
        encoding="utf-8",
    )
    preset_path.write_text(
        yaml.safe_dump(
            _preset(
                sources={"adzuna": {"enabled": True}},
                gate_block={"min_total_rows": 10, "allow_zero_sources": []},
            )
        ),
        encoding="utf-8",
    )
    # Should pass — threshold lowered to 10.
    run_gate(manifest_path, preset_path)


def test_run_gate_raises_on_failure(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    preset_path = tmp_path / "preset.yaml"
    manifest_path.write_text(
        json.dumps(_manifest(total=5, source_counts={"adzuna": 5})),
        encoding="utf-8",
    )
    preset_path.write_text(
        yaml.safe_dump(_preset(sources={"adzuna": {"enabled": True}})),
        encoding="utf-8",
    )
    with pytest.raises(GateError) as ei:
        run_gate(manifest_path, preset_path)
    assert "manifest gate failed" in str(ei.value)


def test_run_gate_missing_manifest(tmp_path: Path) -> None:
    preset_path = tmp_path / "preset.yaml"
    preset_path.write_text(yaml.safe_dump(_preset()), encoding="utf-8")
    with pytest.raises(GateError) as ei:
        run_gate(tmp_path / "absent.json", preset_path)
    assert "not found" in str(ei.value)


def test_run_gate_invalid_gate_block(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    preset_path = tmp_path / "preset.yaml"
    manifest_path.write_text(json.dumps(_manifest()), encoding="utf-8")
    preset_path.write_text(
        yaml.safe_dump(_preset(gate_block={"min_total_rows": -1})),
        encoding="utf-8",
    )
    with pytest.raises(GateError) as ei:
        run_gate(manifest_path, preset_path)
    assert "non-negative integer" in str(ei.value)


def test_run_gate_warn_mode_returns_issues_without_raising(tmp_path: Path) -> None:
    """gate.fail_on_issues=false → run_gate returns issues, never raises."""
    manifest_path = tmp_path / "manifest.json"
    preset_path = tmp_path / "preset.yaml"
    manifest_path.write_text(
        json.dumps(_manifest(total=5, source_counts={"adzuna": 5})),
        encoding="utf-8",
    )
    preset_path.write_text(
        yaml.safe_dump(
            _preset(
                sources={"adzuna": {"enabled": True}, "lever": {"enabled": True}},
                gate_block={"fail_on_issues": False},
            )
        ),
        encoding="utf-8",
    )
    issues = run_gate(manifest_path, preset_path)
    assert any("below threshold" in m for m in issues)
    assert any("source lever" in m for m in issues)


def test_run_gate_warn_mode_returns_empty_on_clean_run(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    preset_path = tmp_path / "preset.yaml"
    manifest_path.write_text(json.dumps(_manifest()), encoding="utf-8")
    preset_path.write_text(
        yaml.safe_dump(_preset(gate_block={"fail_on_issues": False})),
        encoding="utf-8",
    )
    assert run_gate(manifest_path, preset_path) == []


def test_run_gate_rejects_non_bool_fail_on_issues(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    preset_path = tmp_path / "preset.yaml"
    manifest_path.write_text(json.dumps(_manifest()), encoding="utf-8")
    preset_path.write_text(
        yaml.safe_dump(_preset(gate_block={"fail_on_issues": "yes"})),
        encoding="utf-8",
    )
    with pytest.raises(GateError) as ei:
        run_gate(manifest_path, preset_path)
    assert "must be a bool" in str(ei.value)


def test_cli_gate_warn_mode_exits_0_with_warnings(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    preset_path = tmp_path / "preset.yaml"
    manifest_path.write_text(
        json.dumps(_manifest(total=5, source_counts={"adzuna": 5})),
        encoding="utf-8",
    )
    preset_path.write_text(
        yaml.safe_dump(
            _preset(
                sources={"adzuna": {"enabled": True}, "lever": {"enabled": True}},
                gate_block={"fail_on_issues": False},
            )
        ),
        encoding="utf-8",
    )
    result = runner.invoke(
        app,
        ["gate", "--manifest", str(manifest_path), "--preset", str(preset_path)],
    )
    assert result.exit_code == 0
    assert "warn-only" in result.stdout
    assert "source lever" in result.stderr


def test_cli_gate_exits_2_on_failure(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    preset_path = tmp_path / "preset.yaml"
    manifest_path.write_text(
        json.dumps(_manifest(total=5, source_counts={"adzuna": 5})),
        encoding="utf-8",
    )
    preset_path.write_text(
        yaml.safe_dump(_preset(sources={"adzuna": {"enabled": True}})),
        encoding="utf-8",
    )
    result = runner.invoke(
        app,
        ["gate", "--manifest", str(manifest_path), "--preset", str(preset_path)],
    )
    assert result.exit_code == 2
    assert "manifest gate failed" in result.stderr


def test_cli_gate_exits_0_on_pass(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    preset_path = tmp_path / "preset.yaml"
    manifest_path.write_text(json.dumps(_manifest()), encoding="utf-8")
    preset_path.write_text(yaml.safe_dump(_preset()), encoding="utf-8")
    result = runner.invoke(
        app,
        ["gate", "--manifest", str(manifest_path), "--preset", str(preset_path)],
    )
    assert result.exit_code == 0
    assert "gate ok" in result.stdout
