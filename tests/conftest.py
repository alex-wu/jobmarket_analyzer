"""Shared pytest fixtures.

P0 ships VCR scrubbers (so secrets never enter a committed cassette) and a
tmp working-directory fixture. Adapter / integration fixtures land in P1+.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture
def vcr_config() -> dict[str, object]:
    """pytest-recording configuration: scrub all secrets from cassettes."""
    return {
        "filter_query_parameters": [
            ("app_id", "REDACTED"),
            ("app_key", "REDACTED"),
        ],
        "filter_headers": [
            ("authorization", "REDACTED"),
            ("x-api-key", "REDACTED"),
            ("user-agent", "jobpipe-tests"),
        ],
        "record_mode": "none",  # CI never records; refresh locally with --record-mode=new_episodes
    }


@pytest.fixture
def tmp_workdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Run a test inside a clean temp directory."""
    monkeypatch.chdir(tmp_path)
    yield tmp_path
