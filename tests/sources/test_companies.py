"""Tests for the shared ATS-helper module."""

from __future__ import annotations

from pathlib import Path

import pytest

from jobpipe.sources import SourceFetchError
from jobpipe.sources._companies import (
    COUNTRY_ALIASES,
    REMOTE_PATTERNS,
    load_companies_file,
    match_country,
)


def _write(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    return path


def test_load_returns_slugs_for_key(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "c.yaml",
        "greenhouse:\n  - intercom\n  - stripe\nlever:\n  - palantir\n",
    )
    assert load_companies_file(path, "greenhouse") == ["intercom", "stripe"]
    assert load_companies_file(path, "lever") == ["palantir"]


def test_load_returns_empty_for_absent_key(tmp_path: Path) -> None:
    path = _write(tmp_path / "c.yaml", "greenhouse: [intercom]\n")
    assert load_companies_file(path, "lever") == []


def test_load_returns_empty_for_empty_list(tmp_path: Path) -> None:
    path = _write(tmp_path / "c.yaml", "greenhouse: []\n")
    assert load_companies_file(path, "greenhouse") == []


def test_load_strips_whitespace_and_drops_empties(tmp_path: Path) -> None:
    path = _write(tmp_path / "c.yaml", "greenhouse:\n  - '  intercom  '\n  - ''\n  - stripe\n")
    assert load_companies_file(path, "greenhouse") == ["intercom", "stripe"]


def test_load_raises_on_missing_file(tmp_path: Path) -> None:
    with pytest.raises(SourceFetchError, match="not found"):
        load_companies_file(tmp_path / "missing.yaml", "greenhouse")


def test_load_raises_on_invalid_yaml(tmp_path: Path) -> None:
    path = _write(tmp_path / "c.yaml", "greenhouse: [intercom\n")
    with pytest.raises(SourceFetchError, match="not valid YAML"):
        load_companies_file(path, "greenhouse")


def test_load_raises_when_root_is_not_mapping(tmp_path: Path) -> None:
    path = _write(tmp_path / "c.yaml", "- intercom\n- stripe\n")
    with pytest.raises(SourceFetchError, match="must be a YAML mapping"):
        load_companies_file(path, "greenhouse")


def test_load_raises_when_value_is_not_list(tmp_path: Path) -> None:
    path = _write(tmp_path / "c.yaml", "greenhouse: intercom\n")
    with pytest.raises(SourceFetchError, match="must be a list"):
        load_companies_file(path, "greenhouse")


def test_match_country_returns_iso2_for_alias() -> None:
    assert match_country("Dublin, Ireland", ["ie"]) == ("IE", False)
    assert match_country("Berlin", ["de", "ie"]) == ("DE", False)


def test_match_country_is_case_insensitive() -> None:
    assert match_country("DUBLIN", ["ie"]) == ("IE", False)
    assert match_country("dublin", ["IE"]) == ("IE", False)


def test_match_country_returns_none_when_no_alias_hits() -> None:
    assert match_country("San Francisco, CA", ["ie", "de"]) == (None, False)


def test_match_country_returns_none_for_empty_text() -> None:
    assert match_country(None, ["ie"]) == (None, False)
    assert match_country("", ["ie"]) == (None, False)


def test_match_country_remote_europe_anchors_to_first_real_code() -> None:
    assert match_country("Remote (Europe)", ["ie", "remote-europe"]) == ("IE", True)
    assert match_country("EMEA", ["de", "remote-europe"]) == ("DE", True)


def test_match_country_remote_worldwide() -> None:
    assert match_country("Remote", ["ie", "remote-worldwide"]) == ("IE", True)
    assert match_country("Anywhere", ["ie", "remote-worldwide"]) == ("IE", True)


def test_match_country_real_code_wins_over_remote() -> None:
    # "Dublin, Remote" contains both a real alias and a remote pattern.
    # Real-code match must win so we don't lose the country precision.
    assert match_country("Dublin, Remote", ["ie", "remote-europe"]) == ("IE", False)


def test_match_country_returns_none_when_only_pseudo_codes_allowed() -> None:
    # No real ISO-2 to anchor on; remote-only rows can't satisfy strict schema.
    assert match_country("Remote (Europe)", ["remote-europe"]) == (None, True)


def test_match_country_skips_unknown_codes_silently() -> None:
    # "xx" isn't in COUNTRY_ALIASES; helper just ignores it instead of crashing.
    assert match_country("Dublin", ["xx", "ie"]) == ("IE", False)


def test_country_aliases_keys_are_lowercase_iso2() -> None:
    for code in COUNTRY_ALIASES:
        assert code == code.lower()
        assert len(code) == 2


def test_remote_pattern_keys_are_known() -> None:
    assert set(REMOTE_PATTERNS) == {"remote-europe", "remote-worldwide"}
