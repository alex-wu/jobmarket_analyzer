"""Tests for ``validate_preset`` / ``jobpipe validate``.

The validate subcommand is an opt-in stricter check than the default
warn-and-skip behaviour of ``fetch_sources``. It exists for fork users
who want to sanity-check a hand-rolled preset before paying for a real
fetch round-trip.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from typer.testing import CliRunner

from jobpipe.cli import app
from jobpipe.runner import validate_preset

runner = CliRunner()


def _write_preset(tmp_path: Path, body: dict[str, Any]) -> Path:
    out = tmp_path / "preset.yaml"
    out.write_text(yaml.safe_dump(body), encoding="utf-8")
    return out


def test_shipped_preset_validates_clean() -> None:
    """Golden-path regression — shipped preset must always validate.

    Catches the worst kind of merge mistake: breaking the production preset.
    """
    issues = validate_preset(Path("config/runs/data_analyst_ireland.yaml"))
    assert issues == [], f"shipped preset has validation issues: {issues}"


def test_missing_file_returns_single_issue(tmp_path: Path) -> None:
    issues = validate_preset(tmp_path / "absent.yaml")
    assert len(issues) == 1
    assert "not found" in issues[0]


def test_missing_preset_id(tmp_path: Path) -> None:
    issues = validate_preset(_write_preset(tmp_path, {"sources": {}}))
    assert any("preset_id" in i for i in issues)


def test_sources_not_a_mapping(tmp_path: Path) -> None:
    issues = validate_preset(_write_preset(tmp_path, {"preset_id": "x", "sources": ["adzuna"]}))
    assert any("sources" in i for i in issues)


def test_unknown_enabled_source_name(tmp_path: Path) -> None:
    issues = validate_preset(
        _write_preset(
            tmp_path,
            {
                "preset_id": "x",
                "sources": {"linkedin": {"enabled": True}},
            },
        )
    )
    assert any("linkedin" in i and "not a registered adapter" in i for i in issues)


def test_disabled_unknown_source_is_silent(tmp_path: Path) -> None:
    """Validation only inspects enabled adapters — matches fetch_sources."""
    issues = validate_preset(
        _write_preset(
            tmp_path,
            {
                "preset_id": "x",
                "sources": {"linkedin": {"enabled": False}},
            },
        )
    )
    assert issues == []


def test_malformed_source_config_field(tmp_path: Path) -> None:
    """`adzuna.countries` must be a list of strings; passing a single
    string trips the Pydantic validator."""
    issues = validate_preset(
        _write_preset(
            tmp_path,
            {
                "preset_id": "x",
                "sources": {
                    "adzuna": {
                        "enabled": True,
                        "countries": "gb",  # wrong: should be list
                        "keywords": ["data analyst"],
                    }
                },
            },
        )
    )
    assert any("adzuna" in i and "invalid config" in i for i in issues)


def test_publish_partition_by_not_a_list(tmp_path: Path) -> None:
    issues = validate_preset(
        _write_preset(
            tmp_path,
            {
                "preset_id": "x",
                "sources": {},
                "publish": {"partition_by": "country"},
            },
        )
    )
    assert any("partition_by" in i and "list" in i for i in issues)


def test_unknown_benchmark_name(tmp_path: Path) -> None:
    issues = validate_preset(
        _write_preset(
            tmp_path,
            {
                "preset_id": "x",
                "sources": {},
                "benchmarks": {"imf": {"enabled": True}},
            },
        )
    )
    assert any("imf" in i and "not a registered adapter" in i for i in issues)


def test_cli_validate_exits_0_on_pass() -> None:
    result = runner.invoke(
        app,
        ["validate", "--preset", "config/runs/data_analyst_ireland.yaml"],
    )
    assert result.exit_code == 0
    assert "preset ok" in result.stdout


def test_cli_validate_exits_2_on_issues(tmp_path: Path) -> None:
    bad = _write_preset(
        tmp_path,
        {
            "preset_id": "x",
            "sources": {"linkedin": {"enabled": True}},
        },
    )
    result = runner.invoke(app, ["validate", "--preset", str(bad)])
    assert result.exit_code == 2
    assert "linkedin" in result.stderr
