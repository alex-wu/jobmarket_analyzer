"""Direct tests for the pydantic-settings Settings model.

The shipped smoke test (test_smoke.py::test_settings_defaults_load) only
exercises the ``_env_file=None`` defaults path that previously surprised us
([[pitfall_pydantic_env_file_none]] — OS env vars still load even when the
.env path is set to None). These tests pin the rest of the contract so
future env additions don't quietly regress the behaviour.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jobpipe.settings import Settings

_ENV_VARS = (
    "ADZUNA_APP_ID",
    "ADZUNA_APP_KEY",
    "LLM_ENABLED",
    "LLM_BASE_URL",
    "LLM_API_KEY",
    "LLM_MODEL",
    "GH_TOKEN",
)


def _strip_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in _ENV_VARS:
        monkeypatch.delenv(var, raising=False)


def test_all_defaults_are_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    _strip_env(monkeypatch)
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.adzuna_app_id == ""
    assert s.adzuna_app_key == ""
    assert s.llm_enabled is False
    assert s.llm_base_url == ""
    assert s.llm_api_key == ""
    assert s.llm_model == ""
    assert s.gh_token == ""


def test_adzuna_creds_from_os_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pins the documented pitfall: OS env vars still load when _env_file=None."""
    _strip_env(monkeypatch)
    monkeypatch.setenv("ADZUNA_APP_ID", "abc123")
    monkeypatch.setenv("ADZUNA_APP_KEY", "def456")
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.adzuna_app_id == "abc123"
    assert s.adzuna_app_key == "def456"


def test_llm_enabled_parses_string_to_bool(monkeypatch: pytest.MonkeyPatch) -> None:
    _strip_env(monkeypatch)
    monkeypatch.setenv("LLM_ENABLED", "true")
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.llm_enabled is True


def test_env_file_supplies_values(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _strip_env(monkeypatch)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "LLM_BASE_URL=https://api.example/v1\nLLM_MODEL=test-model\n",
        encoding="utf-8",
    )
    s = Settings(_env_file=str(env_file))  # type: ignore[call-arg]
    assert s.llm_base_url == "https://api.example/v1"
    assert s.llm_model == "test-model"


def test_os_env_beats_env_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """pydantic-settings precedence: init kwargs > OS env > .env file > defaults."""
    _strip_env(monkeypatch)
    monkeypatch.setenv("LLM_BASE_URL", "os_value")
    env_file = tmp_path / ".env"
    env_file.write_text("LLM_BASE_URL=file_value\n", encoding="utf-8")
    s = Settings(_env_file=str(env_file))  # type: ignore[call-arg]
    assert s.llm_base_url == "os_value"


def test_unknown_env_keys_are_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    """``model_config.extra='ignore'`` swallows unrelated env vars."""
    _strip_env(monkeypatch)
    monkeypatch.setenv("JOBPIPE_NONEXISTENT_FIELD", "x")
    monkeypatch.setenv("RANDOM_OTHER_VAR", "y")
    # Should not raise.
    Settings(_env_file=None)  # type: ignore[call-arg]
