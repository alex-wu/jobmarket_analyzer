"""Fetcher correctness — HTTP success, cache hit, 404 swallowing, retries."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from jobpipe.work_arrangement.fetcher import (
    AdzunaDetailsError,
    DetailsFetcher,
    _safe_filename,
)


@pytest.fixture
def fake_creds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("jobpipe.work_arrangement.fetcher.settings.adzuna_app_id", "test-id")
    monkeypatch.setattr("jobpipe.work_arrangement.fetcher.settings.adzuna_app_key", "test-key")


def _client(handler: httpx.MockTransport) -> httpx.Client:
    return httpx.Client(transport=handler, timeout=5.0)


def test_fetch_returns_description_on_200(fake_creds: None, tmp_path: Path) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"description": "Fully remote role with great benefits."})

    with DetailsFetcher(
        client=_client(httpx.MockTransport(handler)),
        cache_dir=tmp_path,
        inter_call_sleep=0,
    ) as fetcher:
        body = fetcher.fetch("posting-aaa", "gb", "12345")
    assert body == "Fully remote role with great benefits."


def test_404_returns_none_and_swallows_error(fake_creds: None, tmp_path: Path) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "not found"})

    with DetailsFetcher(
        client=_client(httpx.MockTransport(handler)),
        cache_dir=tmp_path,
        inter_call_sleep=0,
    ) as fetcher:
        body = fetcher.fetch("posting-bbb", "gb", "9999")
    assert body is None


def test_cache_hit_skips_http(fake_creds: None, tmp_path: Path) -> None:
    calls: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        return httpx.Response(200, json={"description": "Hybrid role 3 days office."})

    with DetailsFetcher(
        client=_client(httpx.MockTransport(handler)),
        cache_dir=tmp_path,
        inter_call_sleep=0,
    ) as fetcher:
        body1 = fetcher.fetch("posting-ccc", "gb", "12345")
        body2 = fetcher.fetch("posting-ccc", "gb", "12345")
    assert body1 == body2 == "Hybrid role 3 days office."
    assert len(calls) == 1  # second call served from in-memory cache


def test_disk_cache_persists_across_fetcher_instances(fake_creds: None, tmp_path: Path) -> None:
    calls: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        return httpx.Response(200, json={"description": "On-site role in London office."})

    with DetailsFetcher(
        client=_client(httpx.MockTransport(handler)),
        cache_dir=tmp_path,
        inter_call_sleep=0,
    ) as fetcher_a:
        fetcher_a.fetch("posting-ddd", "gb", "12345")

    # Second fetcher uses the same cache_dir but a fresh client.
    def fresh_handler(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        return httpx.Response(500, text="should not be reached")

    with DetailsFetcher(
        client=_client(httpx.MockTransport(fresh_handler)),
        cache_dir=tmp_path,
        inter_call_sleep=0,
    ) as fetcher_b:
        body = fetcher_b.fetch("posting-ddd", "gb", "12345")
    assert body == "On-site role in London office."
    assert len(calls) == 1  # second fetcher never hit HTTP


def test_retry_then_success(fake_creds: None, tmp_path: Path) -> None:
    statuses = iter([503, 503, 200])

    def handler(_: httpx.Request) -> httpx.Response:
        s = next(statuses)
        if s == 200:
            return httpx.Response(200, json={"description": "Remote-first company."})
        return httpx.Response(s, text="busy")

    with DetailsFetcher(
        client=_client(httpx.MockTransport(handler)),
        cache_dir=tmp_path,
        inter_call_sleep=0,
    ) as fetcher:
        body = fetcher.fetch("posting-eee", "gb", "12345")
    assert body == "Remote-first company."


def test_persistent_500_raises_after_retries(fake_creds: None, tmp_path: Path) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    with DetailsFetcher(
        client=_client(httpx.MockTransport(handler)),
        cache_dir=tmp_path,
        inter_call_sleep=0,
    ) as fetcher:
        with pytest.raises(AdzunaDetailsError):
            fetcher.fetch("posting-fff", "gb", "12345")


def test_empty_description_treated_as_none(fake_creds: None, tmp_path: Path) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"description": ""})

    with DetailsFetcher(
        client=_client(httpx.MockTransport(handler)),
        cache_dir=tmp_path,
        inter_call_sleep=0,
    ) as fetcher:
        body = fetcher.fetch("posting-ggg", "gb", "12345")
    assert body is None


def test_missing_external_id_returns_none_without_http(
    fake_creds: None, tmp_path: Path
) -> None:
    calls: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        return httpx.Response(200, json={"description": "should not be reached"})

    with DetailsFetcher(
        client=_client(httpx.MockTransport(handler)),
        cache_dir=tmp_path,
        inter_call_sleep=0,
    ) as fetcher:
        body = fetcher.fetch("posting-hhh", "gb", "")
    assert body is None
    assert len(calls) == 0


def test_missing_credentials_raises(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("jobpipe.work_arrangement.fetcher.settings.adzuna_app_id", "")
    monkeypatch.setattr("jobpipe.work_arrangement.fetcher.settings.adzuna_app_key", "")

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"description": "x"})

    with DetailsFetcher(
        client=_client(httpx.MockTransport(handler)),
        cache_dir=tmp_path,
        inter_call_sleep=0,
    ) as fetcher:
        with pytest.raises(AdzunaDetailsError, match="ADZUNA_APP_ID"):
            fetcher.fetch("posting-iii", "gb", "12345")


def test_safe_filename_strips_unsafe_chars() -> None:
    assert _safe_filename("abc123") == "abc123.txt"
    assert _safe_filename("a/b\\c.d") == "abcd.txt"
