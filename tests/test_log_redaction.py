"""Tests for the httpx/httpcore credential scrub filter (ADR-015)."""

from __future__ import annotations

import logging

import pytest

from jobpipe.cli import CredentialScrubFilter, _install_credential_scrub


@pytest.fixture
def scrub() -> CredentialScrubFilter:
    return CredentialScrubFilter()


def _make_record(msg: str, args: tuple[object, ...] = ()) -> logging.LogRecord:
    return logging.LogRecord(
        name="httpx",
        level=logging.INFO,
        pathname=__file__,
        lineno=0,
        msg=msg,
        args=args,
        exc_info=None,
    )


def test_filter_scrubs_app_id_and_app_key(scrub: CredentialScrubFilter) -> None:
    record = _make_record(
        "HTTP Request: GET https://api.adzuna.com/v1/api/jobs/gb/search/1"
        "?app_id=real_id_12345&app_key=real_key_67890&what=analyst"
    )
    scrub.filter(record)
    assert "real_id_12345" not in record.getMessage()
    assert "real_key_67890" not in record.getMessage()
    assert "app_id=REDACTED" in record.getMessage()
    assert "app_key=REDACTED" in record.getMessage()
    # Non-credential params survive intact.
    assert "what=analyst" in record.getMessage()


def test_filter_scrubs_within_logrecord_args(scrub: CredentialScrubFilter) -> None:
    record = _make_record(
        "request: %s",
        args=("https://x/?api_key=sekret&q=ok",),
    )
    scrub.filter(record)
    assert "sekret" not in record.getMessage()
    assert "api_key=REDACTED" in record.getMessage()


def test_filter_is_case_insensitive(scrub: CredentialScrubFilter) -> None:
    record = _make_record("GET https://x?App_ID=AAA&APP_KEY=BBB")
    scrub.filter(record)
    msg = record.getMessage()
    assert "AAA" not in msg
    assert "BBB" not in msg


def test_filter_handles_hyphen_form(scrub: CredentialScrubFilter) -> None:
    record = _make_record("GET https://x?api-key=abc123")
    scrub.filter(record)
    assert "abc123" not in record.getMessage()
    assert "api-key=REDACTED" in record.getMessage()


def test_filter_returns_true_always(scrub: CredentialScrubFilter) -> None:
    assert scrub.filter(_make_record("nothing to scrub here")) is True


def test_filter_leaves_non_credential_records_unchanged(
    scrub: CredentialScrubFilter,
) -> None:
    record = _make_record("just a normal log line with no = sign at all")
    original = record.msg
    scrub.filter(record)
    assert record.msg == original


def test_install_attaches_filter_idempotently() -> None:
    httpx_logger = logging.getLogger("httpx")
    httpcore_logger = logging.getLogger("httpcore")
    # Strip any pre-existing filter so the test is hermetic.
    for lg in (httpx_logger, httpcore_logger):
        for f in list(lg.filters):
            if isinstance(f, CredentialScrubFilter):
                lg.removeFilter(f)

    _install_credential_scrub()
    _install_credential_scrub()  # second call must not double-attach

    for lg in (httpx_logger, httpcore_logger):
        scrubbers = [f for f in lg.filters if isinstance(f, CredentialScrubFilter)]
        assert len(scrubbers) == 1


def test_installed_filter_redacts_caplog_capture(
    caplog: pytest.LogCaptureFixture,
) -> None:
    _install_credential_scrub()
    httpx_logger = logging.getLogger("httpx")
    with caplog.at_level(logging.INFO, logger="httpx"):
        httpx_logger.info("HTTP Request: GET https://api.adzuna.com/?app_id=ID123&app_key=KEY456")
    joined = "\n".join(r.getMessage() for r in caplog.records)
    assert "ID123" not in joined
    assert "KEY456" not in joined
    assert "REDACTED" in joined
