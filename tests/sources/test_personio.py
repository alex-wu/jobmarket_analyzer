"""Personio XML adapter tests — fixtures + httpx.MockTransport (no live HTTP)."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from jobpipe.schemas import PostingSchema
from jobpipe.sources import SourceFetchError
from jobpipe.sources.personio import PersonioAdapter, PersonioConfig

FIXTURES = Path(__file__).parent.parent / "fixtures" / "personio"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _mock(handler: httpx.MockTransport) -> httpx.Client:
    return httpx.Client(transport=handler, timeout=5.0)


def _companies(tmp_path: Path, slugs: list[str]) -> Path:
    body = "personio:\n" + "".join(f"  - {s}\n" for s in slugs) if slugs else "personio: []\n"
    p = tmp_path / "dublin_tech.yaml"
    p.write_text(body, encoding="utf-8")
    return p


def test_fetch_returns_normalised_dataframe(tmp_path: Path) -> None:
    cf = _companies(tmp_path, ["exampleco"])

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=_load("feed_dublin.xml"))

    cfg = PersonioConfig(
        companies_file=cf,
        keywords=["analyst", "analytics"],
        countries=["ie"],
    )
    df = PersonioAdapter().fetch(cfg, client=_mock(httpx.MockTransport(handler)))
    # 5 fixture positions: 2 Dublin analyst rows kept; Munich engineer dropped (country),
    # empty-id and empty-name positions dropped (defensive guards).
    assert len(df) == 2
    PostingSchema.validate(df, lazy=True)
    assert set(df["title"]) == {"Senior Data Analyst", "Analytics Engineer (Remote-friendly)"}


def test_fetch_constructs_posting_url(tmp_path: Path) -> None:
    cf = _companies(tmp_path, ["exampleco"])

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=_load("feed_dublin.xml"))

    cfg = PersonioConfig(companies_file=cf, keywords=["data analyst"], countries=["ie"])
    df = PersonioAdapter().fetch(cfg, client=_mock(httpx.MockTransport(handler)))
    row = df.iloc[0]
    assert row["posting_url"] == "https://exampleco.jobs.personio.de/job/4001001"
    assert row["source"] == "personio"
    assert row["company"] == "exampleco"
    assert row["country"] == "IE"


def test_fetch_falls_back_to_ingested_at_for_missing_create_date(tmp_path: Path) -> None:
    cf = _companies(tmp_path, ["exampleco"])
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<workzag-jobs>"
        "<position>"
        "<id>9001</id>"
        "<office>Dublin</office>"
        "<name>Data Analyst</name>"
        "<createDate></createDate>"
        "</position>"
        "</workzag-jobs>"
    )

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=body)

    cfg = PersonioConfig(companies_file=cf, keywords=["analyst"], countries=["ie"])
    df = PersonioAdapter().fetch(cfg, client=_mock(httpx.MockTransport(handler)))
    assert len(df) == 1
    # Just confirm posted_at is a valid timestamp; we don't pin the exact value.
    PostingSchema.validate(df, lazy=True)


def test_fetch_skips_slug_on_404_and_continues(tmp_path: Path) -> None:
    cf = _companies(tmp_path, ["dead", "exampleco"])
    calls: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        slug = req.url.host.split(".")[0]
        calls.append(slug)
        if slug == "dead":
            return httpx.Response(404)
        return httpx.Response(200, text=_load("feed_dublin.xml"))

    cfg = PersonioConfig(
        companies_file=cf,
        keywords=["analyst", "analytics"],
        countries=["ie"],
    )
    df = PersonioAdapter().fetch(cfg, client=_mock(httpx.MockTransport(handler)))
    assert calls == ["dead", "exampleco"]
    assert len(df) == 2


def test_fetch_handles_malformed_xml_softly(tmp_path: Path) -> None:
    cf = _companies(tmp_path, ["broken", "exampleco"])

    def handler(req: httpx.Request) -> httpx.Response:
        slug = req.url.host.split(".")[0]
        if slug == "broken":
            return httpx.Response(200, text="<workzag-jobs><position>UNCLOSED")
        return httpx.Response(200, text=_load("feed_dublin.xml"))

    cfg = PersonioConfig(
        companies_file=cf,
        keywords=["analyst", "analytics"],
        countries=["ie"],
    )
    df = PersonioAdapter().fetch(cfg, client=_mock(httpx.MockTransport(handler)))
    # Malformed slug yields zero rows, exampleco still contributes.
    assert len(df) == 2


def test_fetch_raises_on_persistent_5xx(tmp_path: Path) -> None:
    cf = _companies(tmp_path, ["exampleco"])

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    cfg = PersonioConfig(companies_file=cf, keywords=["analyst"], countries=["ie"])
    with pytest.raises(SourceFetchError, match="personio"):
        PersonioAdapter().fetch(cfg, client=_mock(httpx.MockTransport(handler)))


def test_fetch_returns_empty_for_feed_with_no_positions(tmp_path: Path) -> None:
    cf = _companies(tmp_path, ["exampleco"])

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=_load("feed_empty.xml"))

    cfg = PersonioConfig(companies_file=cf, keywords=["analyst"], countries=["ie"])
    df = PersonioAdapter().fetch(cfg, client=_mock(httpx.MockTransport(handler)))
    assert df.empty


def test_fetch_returns_empty_when_no_slugs(tmp_path: Path) -> None:
    cf = _companies(tmp_path, [])
    cfg = PersonioConfig(companies_file=cf, keywords=["analyst"], countries=["ie"])
    df = PersonioAdapter().fetch(cfg)
    assert df.empty


def test_fetch_filters_by_country(tmp_path: Path) -> None:
    cf = _companies(tmp_path, ["exampleco"])

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=_load("feed_dublin.xml"))

    # Only DE allowed → only the Munich row survives the country filter
    # (then fails the keyword filter "analyst" but passes if keyword is empty).
    cfg = PersonioConfig(companies_file=cf, keywords=[], countries=["de"])
    df = PersonioAdapter().fetch(cfg, client=_mock(httpx.MockTransport(handler)))
    assert len(df) == 1
    assert df.iloc[0]["title"] == "Backend Engineer"
    assert df.iloc[0]["country"] == "DE"


def test_fetch_caps_at_max_results(tmp_path: Path) -> None:
    cf = _companies(tmp_path, ["exampleco"])

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=_load("feed_dublin.xml"))

    cfg = PersonioConfig(
        companies_file=cf,
        keywords=["analyst", "analytics"],
        countries=["ie"],
        max_results=1,
    )
    df = PersonioAdapter().fetch(cfg, client=_mock(httpx.MockTransport(handler)))
    assert len(df) == 1


def test_fetch_hits_documented_endpoint_shape(tmp_path: Path) -> None:
    cf = _companies(tmp_path, ["exampleco"])
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(200, text=_load("feed_empty.xml"))

    cfg = PersonioConfig(companies_file=cf, keywords=["analyst"], countries=["ie"])
    PersonioAdapter().fetch(cfg, client=_mock(httpx.MockTransport(handler)))
    assert seen[0].url.host == "exampleco.jobs.personio.de"
    assert seen[0].url.path == "/xml"


def test_adapter_self_registered_on_import() -> None:
    import jobpipe.sources.personio  # noqa: F401
    from jobpipe import sources

    assert "personio" in sources.names()
    assert sources.get("personio").name == "personio"
