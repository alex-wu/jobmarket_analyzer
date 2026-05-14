from __future__ import annotations

import pytest

from jobpipe import llm
from jobpipe.settings import Settings


def test_classify_raises_unavailable_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm, "settings", Settings(_env_file=None, llm_enabled=False))  # type: ignore[call-arg]
    with pytest.raises(llm.LLMUnavailableError):
        llm.classify_title_to_isco("data analyst", ["2511"])


def test_classify_raises_not_implemented_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        llm,
        "settings",
        Settings(  # type: ignore[call-arg]
            _env_file=None,
            llm_enabled=True,
            llm_base_url="http://fake",
            llm_api_key="sk-fake",
            llm_model="gpt-fake",
        ),
    )
    with pytest.raises(NotImplementedError):
        llm.classify_title_to_isco("data analyst", ["2511", "2521"])


def test_unavailable_inherits_runtime_error() -> None:
    assert issubclass(llm.LLMUnavailableError, RuntimeError)
