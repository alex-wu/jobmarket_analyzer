"""Adzuna source adapter tests.

Live HTTP would require API credentials, so tests inject an ``httpx.MockTransport``
that replays canned JSON fixtures. The fixtures live under ``tests/fixtures/adzuna/``
and reflect the Adzuna response shape documented at https://developer.adzuna.com/.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pandas as pd
import pytest

from jobpipe.schemas import PostingSchema
from jobpipe.sources import SourceFetchError
from jobpipe.sources.adzuna import BASE_URL, AdzunaAdapter, AdzunaConfig

FIXTURES = Path(__file__).parent.parent / "fixtures" / "adzuna"


def _load(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def fake_creds(monkeypatch: pytest.MonkeyPatch) -> None:
    """Populate Adzuna credentials so the adapter doesn't bail early."""
    monkeypatch.setattr("jobpipe.sources.adzuna.settings.adzuna_app_id", "test-id")
    monkeypatch.setattr("jobpipe.sources.adzuna.settings.adzuna_app_key", "test-key")


def _mock_client(handler: httpx.MockTransport) -> httpx.Client:
    return httpx.Client(transport=handler, timeout=5.0)


def test_fetch_returns_normalised_dataframe(fake_creds: None) -> None:
    page1 = _load("search_page1.json")
    page2 = _load("search_page2_empty.json")

    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        page = int(request.url.path.rsplit("/", 1)[-1])
        return httpx.Response(200, json=page1 if page == 1 else page2)

    cfg = AdzunaConfig(keywords=["data analyst"], countries=["gb"], max_pages=2)
    df = AdzunaAdapter().fetch(cfg, client=_mock_client(httpx.MockTransport(handler)))

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 3
    # P1 uses partial validation (strict=False); P2 will flip to strict=True.
    PostingSchema.validate(df, lazy=True)

    # First call hits the documented endpoint shape and includes credentials + keyword.
    first = calls[0]
    assert first.url.path == "/v1/api/jobs/gb/search/1"
    assert first.url.host == httpx.URL(BASE_URL).host
    assert first.url.params["app_id"] == "test-id"
    assert first.url.params["app_key"] == "test-key"
    assert first.url.params["what"] == "data analyst"


def test_fetch_required_fields(fake_creds: None) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_load("search_page1.json"))

    cfg = AdzunaConfig(keywords=["data analyst"], countries=["gb"], max_pages=1)
    df = AdzunaAdapter().fetch(cfg, client=_mock_client(httpx.MockTransport(handler)))

    row = df.iloc[0]
    assert row["source"] == "adzuna"
    assert row["posting_id"]  # sha1 hex, never empty
    assert row["posting_url"].startswith("http")
    assert row["country"] == "GB"
    assert row["title"] == "Senior Data Analyst"
    assert row["company"] == "Acme Analytics Ltd"
    assert row["salary_period"] == "annual"
    assert row["salary_min_eur"] == 55000.0
    assert row["salary_max_eur"] == 70000.0
    assert row["salary_annual_eur_p50"] == 62500.0


def test_fetch_passes_max_days_old_when_set(fake_creds: None) -> None:
    page = _load("search_page1.json")
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=page)

    cfg = AdzunaConfig(keywords=["data analyst"], countries=["gb"], max_pages=1, max_days_old=180)
    AdzunaAdapter().fetch(cfg, client=_mock_client(httpx.MockTransport(handler)))

    assert calls[0].url.params["max_days_old"] == "180"


def test_fetch_omits_max_days_old_when_unset(fake_creds: None) -> None:
    page = _load("search_page1.json")
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=page)

    cfg = AdzunaConfig(keywords=["data analyst"], countries=["gb"], max_pages=1)
    AdzunaAdapter().fetch(cfg, client=_mock_client(httpx.MockTransport(handler)))

    assert "max_days_old" not in calls[0].url.params


def test_fetch_handles_missing_salary(fake_creds: None) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_load("search_page1.json"))

    cfg = AdzunaConfig(keywords=["data analyst"], countries=["gb"], max_pages=1)
    df = AdzunaAdapter().fetch(cfg, client=_mock_client(httpx.MockTransport(handler)))

    no_salary = df[df["title"] == "BI Analyst (Remote)"].iloc[0]
    assert pd.isna(no_salary["salary_min_eur"])
    assert pd.isna(no_salary["salary_max_eur"])
    assert pd.isna(no_salary["salary_annual_eur_p50"])


def test_fetch_short_circuits_when_page_is_short(fake_creds: None) -> None:
    """Adzuna returns ``len(results) < results_per_page`` on the last page → stop paging."""
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=_load("search_page1.json"))

    cfg = AdzunaConfig(
        keywords=["data analyst"],
        countries=["gb"],
        results_per_page=50,  # fixture has 3 rows, so 3 < 50 → stop after page 1
        max_pages=5,
    )
    AdzunaAdapter().fetch(cfg, client=_mock_client(httpx.MockTransport(handler)))
    assert calls == 1


def test_fetch_raises_on_missing_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("jobpipe.sources.adzuna.settings.adzuna_app_id", "")
    monkeypatch.setattr("jobpipe.sources.adzuna.settings.adzuna_app_key", "")

    cfg = AdzunaConfig(keywords=["x"], countries=["gb"])
    with pytest.raises(SourceFetchError, match="missing"):
        AdzunaAdapter().fetch(cfg)


def test_fetch_raises_typed_error_on_http_5xx(fake_creds: None) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="internal")

    cfg = AdzunaConfig(
        keywords=["x"],
        countries=["gb"],
        max_pages=1,
    )
    with pytest.raises(SourceFetchError, match="adzuna"):
        AdzunaAdapter().fetch(cfg, client=_mock_client(httpx.MockTransport(handler)))


def test_fetch_returns_empty_frame_when_no_results(fake_creds: None) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": [], "count": 0})

    cfg = AdzunaConfig(keywords=["x"], countries=["gb"], max_pages=1)
    df = AdzunaAdapter().fetch(cfg, client=_mock_client(httpx.MockTransport(handler)))
    assert df.empty


def test_fetch_dedupes_overlapping_keywords(fake_creds: None) -> None:
    """A single posting matched by multiple keywords must not duplicate in output."""

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_load("search_page1.json"))

    cfg = AdzunaConfig(
        keywords=["data analyst", "analytics engineer"],
        countries=["gb"],
        max_pages=1,
    )
    df = AdzunaAdapter().fetch(cfg, client=_mock_client(httpx.MockTransport(handler)))

    # Fixture has 3 postings; same handler returns them for both keywords → 6 raw, 3 unique.
    assert df["posting_id"].is_unique
    assert len(df) == 3
    PostingSchema.validate(df, lazy=True)


def test_max_results_caps_output(fake_creds: None) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_load("search_page1.json"))

    cfg = AdzunaConfig(keywords=["x"], countries=["gb"], max_pages=1, max_results=2)
    df = AdzunaAdapter().fetch(cfg, client=_mock_client(httpx.MockTransport(handler)))
    assert len(df) == 2


def test_adapter_self_registered_on_import() -> None:
    import jobpipe.sources.adzuna  # noqa: F401
    from jobpipe import sources

    assert "adzuna" in sources.names()
    assert sources.get("adzuna").name == "adzuna"
