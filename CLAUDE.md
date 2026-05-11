# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Status

Pre-implementation. Repo contains only `Project_Objectives.md` (the spec) and this file. No source, no `pyproject.toml`, no `uv.lock`. Build is phase-gated (P0–P10 in spec §16); current phase is **before P0**.

`Project_Objectives.md` is authoritative — when it conflicts with this file or with assumptions, the spec wins.

## Project Overview

Job Market Intelligence Pipeline. Given a keyword or job-description text, ingest postings from multiple sources (JobSpy-covered boards, Adzuna, USAJobs, ATS endpoints, optional long-tail crawl), normalize into a single corpus (DuckDB + Parquet), and emit salary / skill / demand analytics with BLS OEWS benchmark deltas. Single-user, self-hosted, no paid SaaS. Target runtime: local machine or GitHub Pages/Actions.

## Commands

Tooling is fixed by spec §4 — `uv` for envs, `dagster` for orchestration, `pytest`/`ruff`/`mypy` for gates. None of these run yet (no `pyproject.toml`). Once P0 lands:

- Env sync: `uv sync` (lockfile-first; never `pip install` outside this)
- Dev UI: `dagster dev` — Dagster web UI at `http://localhost:3000`
- Materialize one asset: `dagster asset materialize --select keyword_report --partition <YYYY-MM-DD>`
- Tests (all): `pytest`
- Tests (single): `pytest tests/test_salary.py::test_name -x`
- Lint: `ruff check`
- Type-check: `mypy --strict src/jobpipe`
- Container: `podman build -t jobpipe .` (Docker compatible)

CI gates per spec §NFR-7: `ruff check` clean, `mypy --strict` exit 0, `pytest -x` passes, ≥80% line / 70% branch coverage.

## Architecture

Asset-centric Dagster pipeline. Every artifact — raw postings, reference data, enriched corpus, reports — is a Dagster software-defined asset with explicit deps. Re-runs, partitioning, retries, and lineage come from Dagster; do not hand-roll them.

Flow: `run_plan` → per-source raw assets (fail-isolated) → `raw_postings` (via dlt → DuckDB) → `enriched_postings` (salary norm → currency/annualize → title→SOC → geo CBSA → skills → MinHash dedup, each step Pandera-validated) → `keyword_report` (joins BLS OEWS for benchmark delta, emits Markdown + JSON + CSV under `out/{run_id}/`).

Source assets and their backing library (spec §4.1):
- `jobspy_postings` → JobSpy library (Indeed, LinkedIn, Glassdoor, Google, ZipRecruiter, Bayt, Naukri — one call, normalized DF with parsed salary fields)
- `adzuna_postings`, `usajobs_postings` → dlt `rest_api` source (declarative pagination/auth)
- `ats_postings` → direct `httpx` to Greenhouse/Lever/Ashby public JSON endpoints; companies listed in `config/companies.yaml`
- `longtail_postings` (optional, P8) → Crawl4AI with `LLMExtractionStrategy`
- `bls_oews`, `onet`, `fx_rates` → reference data assets

Module layout target: `src/jobpipe/{settings,cli,llm,schemas}.py` + `src/jobpipe/defs/{sources,refs,enrich,report}/`. Total target ~1,400 LoC (spec §12.2).

Storage: DuckDB tables `raw.*` (one per source, dlt-managed), `enriched.postings`, `ref.*` (soc_taxonomy, cbsa_lookup, bls_oews, fx_rates), `cache.salary_parse`. Schema is the `PostingSchema` Pandera class in spec §9.1.

## Conventions

Load-bearing rules — most are not derivable from code once written:

**Hard exclusions (enforced by `tests/test_license_audit.py`):**
- NEVER install `dlthub` (proprietary; adds paid Pro/Scale/Enterprise features). Only `dlt`.
- NEVER install `dagster-cloud` (paid Dagster+ hosting). Only `dagster` + `dagster-webserver`.
- If `crawl4ai` is in `pyproject.toml`, README.md or NOTICE.md MUST include the "Powered by Crawl4AI" badge or text credit (Apache-2.0 + attribution clause, v0.5.0+). If skipped, remove `crawl4ai` entirely.

**Library leverage (spec §22):**
- Use library defaults aggressively. Do NOT hand-roll retries (Dagster `RetryPolicy`), schema migration (dlt auto-evolves), TLS impersonation (JobSpy bundles `tls-client`), or rate limiting (JobSpy internal + Dagster cooldown).
- Don't fight the libraries. If a library's design pushes back on a requirement, surface it as an open question rather than working around it.
- No new top-level dep without a one-line justification.
- Pin exact versions in `uv.lock`. Never `~=` or `>=` for the libraries in spec §4.1.

**LLM is optional, always:**
- Every transformation has a non-LLM fallback. Pipeline must materialize end-to-end with `LLM_ENABLED=false` (spec NFR-10, acceptance #7).
- `LLMClient` wraps the `openai` SDK with `base_url` + `api_key` from settings — works with any OpenAI-compatible endpoint (OpenAI, Anthropic via gateway, Ollama, vLLM, LM Studio). Never hard-depend on a specific provider.
- LLM only fills gaps the deterministic path can't (e.g., salary parse on regex miss).

**Module purity:**
- `defs/enrich/*` must be pure: DataFrames in, DataFrames out. No HTTP, no FS, no DB.
- All side effects live in `defs/sources/*` and Dagster resources (`defs/resources.py`).

**Source assets fail-isolated:** one source's failure does not abort the run; downstream `raw_postings` consumes whichever succeeded. But a run with 0 postings across all sources MUST fail loudly (not silently produce an empty report).

**Re-runs are idempotent:** raw assets use Dagster `DailyPartitionsDefinition` + dlt incremental load. Re-materializing the same partition must not duplicate rows (acceptance #4).

**Testing discipline:**
- VCR cassettes (via `pytest-recording`) recorded BEFORE writing a parser. Test against the fixture, not live HTTP. No live HTTP in CI.
- LLM tests use `pytest-httpserver` fake — never real LLM calls.
- Dagster assets tested via `materialize_to_memory` with mocked resources.

**Phase-gated build (spec §16):** P0 → P10 each has its own acceptance criteria. One PR per phase. Each PR: code + tests + README delta + CHANGELOG entry. Do not skip ahead.

**Secrets:** env / `.env` only (gitignored), surfaced via `pydantic-settings`. Env vars catalogued in spec §14.1 (notable: `ADZUNA_APP_ID`/`KEY`, `USAJOBS_USER_AGENT` with email, `LLM_BASE_URL`/`API_KEY`/`MODEL`, `JOBSPY_PROXIES`).
