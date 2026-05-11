"""Reject PRs that introduce excluded packages.

The exclusions exist because they would silently make the project paid-tier,
proprietary-coupled, or non-runnable on GitHub Actions. See DECISIONS.md.
"""

from __future__ import annotations

from pathlib import Path

import pytest

EXCLUDED_PACKAGES = {
    "dlthub",  # proprietary fork of dlt
    "dagster-cloud",  # paid Dagster hosting
    "dagster-plus",  # alias of dagster-cloud
    "firecrawl-py",  # paid scraping service
}

PROJECT_ROOT = Path(__file__).parent.parent


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


@pytest.mark.parametrize("file", ["pyproject.toml", "uv.lock"])
def test_no_excluded_packages(file: str) -> None:
    contents = _read(PROJECT_ROOT / file).lower()
    if not contents:
        pytest.skip(f"{file} not present yet")

    for pkg in EXCLUDED_PACKAGES:
        # Match `name = "pkg"` (uv.lock) or quoted entries in dep arrays (pyproject).
        bad_patterns = [
            f'name = "{pkg}"',
            f'"{pkg}"',
            f"'{pkg}'",
            f'"{pkg}>=',
            f'"{pkg}~=',
            f'"{pkg}==',
        ]
        for pattern in bad_patterns:
            assert pattern not in contents, (
                f"Excluded package {pkg!r} found in {file}. "
                f"See DECISIONS.md for why this is rejected."
            )
