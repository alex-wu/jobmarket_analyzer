"""Trivial smoke tests so P0 CI has something to run."""

from __future__ import annotations

import pandas as pd
import pytest
from typer.testing import CliRunner

import jobpipe
from jobpipe import benchmarks, sources
from jobpipe.cli import app
from jobpipe.normalise import run
from jobpipe.schemas import BenchmarkSchema, PostingSchema
from jobpipe.settings import Settings

runner = CliRunner()


def test_version_is_a_string() -> None:
    assert isinstance(jobpipe.__version__, str)
    assert jobpipe.__version__.count(".") >= 2


def test_cli_app_is_importable() -> None:
    assert app is not None
    assert app.info.name == "jobpipe"


def test_cli_version_flag_prints_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert jobpipe.__version__ in result.stdout


def test_cli_fetch_errors_on_missing_preset() -> None:
    result = runner.invoke(app, ["fetch", "--preset", "definitely_missing.yaml"])
    assert result.exit_code == 2
    assert "preset" in result.stderr.lower()


def test_cli_normalise_errors_on_missing_preset() -> None:
    result = runner.invoke(app, ["normalise", "--preset", "definitely_missing.yaml"])
    assert result.exit_code == 2
    assert "preset" in result.stderr.lower()


def test_cli_publish_skeleton_exits_ok() -> None:
    result = runner.invoke(app, ["publish", "--preset", "x.yaml"])
    assert result.exit_code == 0
    assert "publish" in result.stdout


def test_settings_defaults_load() -> None:
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.llm_enabled is False
    assert s.adzuna_app_id == ""


def test_schemas_are_importable() -> None:
    assert PostingSchema is not None
    assert BenchmarkSchema is not None


def test_source_registry_lists_known_adapters() -> None:
    # P1 registers adzuna; subsequent phases register more.
    assert "adzuna" in sources.names()


def test_source_registry_get_raises_for_unknown() -> None:
    with pytest.raises(KeyError):
        sources.get("nope")


def test_source_register_decorator_registers_valid_adapter() -> None:
    @sources.register("smoke_source")
    class _SmokeSource:
        name = "smoke_source"
        config_model = sources.SourceConfig

        def fetch(self, config: sources.SourceConfig) -> pd.DataFrame:
            return pd.DataFrame()

    try:
        assert "smoke_source" in sources.names()
        assert sources.get("smoke_source").name == "smoke_source"
    finally:
        sources._REGISTRY.pop("smoke_source", None)


def test_source_register_rejects_non_adapter() -> None:
    with pytest.raises(TypeError):

        @sources.register("bad")
        class _Bad:  # missing the Protocol attributes / methods
            pass


def test_benchmark_registry_is_empty_at_p0() -> None:
    assert benchmarks.names() == []


def test_benchmark_registry_get_raises_for_unknown() -> None:
    with pytest.raises(KeyError):
        benchmarks.get("nope")


def test_benchmark_register_decorator_registers_valid_adapter() -> None:
    @benchmarks.register("smoke_bench")
    class _SmokeBench:
        name = "smoke_bench"
        config_model = benchmarks.BenchmarkConfig

        def fetch(self, config: benchmarks.BenchmarkConfig) -> pd.DataFrame:
            return pd.DataFrame()

    try:
        assert "smoke_bench" in benchmarks.names()
        assert benchmarks.get("smoke_bench").name == "smoke_bench"
    finally:
        benchmarks._REGISTRY.pop("smoke_bench", None)


def test_normalise_run_is_empty_safe() -> None:
    out = run(pd.DataFrame(), rates={"EUR": 1.0})
    assert out.empty
