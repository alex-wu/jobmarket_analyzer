# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed — Pre-P5 cleanup (2026-05-15)
- **Security: httpx URL credential redaction.** `CredentialScrubFilter` installed on the `httpx` / `httpcore` loggers from `src/jobpipe/cli.py` at every CLI entry point. Replaces `app_id` / `app_key` / `api_key` / `api-key` query-param values with `REDACTED` in log records before any handler sees them. Tested centrally in `tests/test_log_redaction.py`. Closes the pre-P5 must-fix; `--verbose` runs are now safe to ship to GitHub Actions logs. See [ADR-015](DECISIONS.md#adr-015--httpx-credential-redaction-filter-on-the-cli-logger).
- **Scope: HN Algolia + LLM client descoped from v1.** `hn_algolia` block removed from `config/runs/data_analyst_ireland.yaml`; `LLM_*` env vars removed from `.env.example`; `src/jobpipe/llm.py` retained as a documented stub so a post-v1 PR can drop in the real client without rippling through callers. See [ADR-013](DECISIONS.md#adr-013--hn-algolia--llm-client-descoped-from-v1).
- **Privacy: local AI-collaboration scaffolding gitignored.** `CLAUDE.md`, `.claude/`, `docs/sessions/`, `docs/history/` all untracked + gitignored. Load-bearing content migrated to public docs: hard rules + testing discipline + git workflow → `CONTRIBUTING.md`; module layout → `docs/architecture.md`; open-questions list → new `docs/open-questions.md`. See [ADR-014](DECISIONS.md#adr-014--local-only-files-excluded-from-the-public-repo).
- **Deploy: GitHub Pages strategy locked.** Monorepo with `site/`, deployed via `actions/deploy-pages` (Pages source = "GitHub Actions"). One-time manual GitHub config checklisted in new `docs/github-setup.md`. See [ADR-016](DECISIONS.md#adr-016--github-pages-deploy-via-actionsdeploy-pages-from-the-monorepo).
- **Docs: README + architecture.md updated** to point at the new ADRs, drop HN references, add a Deploy section, and link to `docs/open-questions.md` as the single source of truth for unresolved items.
- **Test robustness:** `tests/test_smoke.py::test_settings_defaults_load` now clears `ADZUNA_*` / `LLM_*` / `GH_TOKEN` via `monkeypatch.delenv` before asserting defaults — `Settings(_env_file=None)` only disables `.env` reading, not OS env var pickup, so a developer with those vars set in their shell was getting a false failure.

### Added — P4 (2026-05-14)
- `src/jobpipe/isco/` — rapidfuzz-based ISCO-08 tagger. `loader.py` reads the static ESCO snapshot (cached per resolved path); `tagger.py` runs `rapidfuzz.process.extractOne(title, candidates, scorer=token_set_ratio, score_cutoff=88)` to populate `isco_code` / `isco_match_method` / `isco_match_score` on postings. Pure DataFrame in / DataFrame out, no HTTP at runtime.
- `config/esco/isco08_labels.parquet` — 2 137 labels × 436 unique 4-digit ISCO codes, built from ESCO v1.2.1 via `scripts/build_esco_snapshot.py`. The snapshot walks the ISCO concept tree from the 10 major groups (ESCO's `/api/search` and `/api/resource/concept?isInScheme=...` paginations both cap at offset=100). Provenance + EUPL-1.2 attribution in `config/esco/README.md`.
- `src/jobpipe/llm.py` — stub interface. `LLMUnavailableError` + `classify_title_to_isco(title, allowed_codes)`. Raises immediately under `LLM_ENABLED=false`; the real OpenAI-compatible client lands in a follow-up. Not invoked anywhere in this phase — exists to lock the contract.
- `src/jobpipe/benchmarks/_common.py` — `last_fetch_mtime` (newest parquet under an adapter dir), `should_skip(now, last_fetch, min_interval_hours)` (pure throttle), `convert_benchmark_to_eur` (per-row FX via the `currency` column; drops rows whose currency is missing from the ECB feed).
- `src/jobpipe/benchmarks/cso.py` — CSO Ireland `EHQ03` PxStat JSON-stat 2.0 adapter. EUR-native (no FX). Weekly earnings annualised x52. **Caveat documented in the module docstring + `docs/adding-a-benchmark.md`:** the cube lacks a 4-digit ISCO axis; it exposes a 3-bucket "Type of Employee" classification (managers+profs / clerical+sales / manual). The adapter maps each requested ISCO code to the umbrella bucket via the leading digit.
- `src/jobpipe/benchmarks/oecd.py` — generic OECD SDMX-JSON 2.0 adapter, configurable via `dataflow_id` + `key`. Handles `UNIT_MEASURE` per-observation currency attribute. **Disabled by default** — `sdmx.oecd.org` is Cloudflare-protected and returns 403 + HTML to unauthenticated GH-Actions workers. Adapter detects this (content-type sniff) and returns an empty frame to keep the run going.
- `src/jobpipe/benchmarks/eurostat.py` — Eurostat `earn_ses_annual` JSON-stat 2.0 adapter. Strips the `OC` prefix on the `isco08` dimension and keeps only 4-digit leaves (aggregate buckets `OC25`, `OC1-5` etc. are dropped). Auto-selects the latest SES vintage in the response; the 4-year survey lag should be flagged in the dashboard.
- `src/jobpipe/runner.py` — `fetch_benchmarks(preset, out_root, now=None)` mirrors `fetch_sources`: fail-isolated per adapter, throttled per `min_interval_hours` via mtime of the newest parquet under `data/raw/benchmarks/<name>/`. `run_fetch` wires it in after the postings write; `run_normalise` concats each adapter's latest parquet into a sibling `data/enriched/<run_id>/benchmarks.parquet`.
- `BenchmarkAdapter` Protocol's `fetch` signature now declares an optional `rates: dict[str, float] | None = None` kwarg so adapters that need FX can consume rates without breaking the interface.
- `BenchmarkSchema.Config.strict` flipped to `True` now that all three adapters land.
- Preset `config/runs/data_analyst_ireland.yaml`: `cso` + `eurostat` flipped to `enabled: true` with per-bench `min_interval_hours`; `oecd` block kept with rationale for staying disabled.
- `tests/test_smoke.py` benchmark-registry assertion replaces the P0 empty-registry stub.
- `scripts/build_esco_snapshot.py` — one-shot ESCO snapshot builder, not invoked at pipeline runtime. Re-run when ESCO publishes a new classification version.
- 59 new tests under `tests/isco/`, `tests/benchmarks/`, `tests/test_llm_stub.py` plus runner extensions; 223 tests total, 92.32% coverage.

### Decided — P4 scope shifts (2026-05-14)
- **HN Algolia deferred to a follow-up PR.** Needs the real LLM client (free-text "Who is hiring?" comments aren't usefully parseable without extraction). The `llm.py` stub locks the calling contract so the follow-up is a drop-in.
- **OECD adapter ships disabled in the preset.** Cloudflare bot-protection on `sdmx.oecd.org` returns 403 + HTML interstitial to anonymous CI workers. The adapter is fully implemented and fixture-tested; a follow-up needs an auth header / CSV mirror / fixed-egress proxy before flipping it on.
- **ESCO pagination is broken.** Both `/api/search?type=occupation` and `/api/resource/concept?isInScheme=...` cap at offset=100 as of v1.2.1. `scripts/build_esco_snapshot.py` walks the ISCO concept tree instead (which works) and gets full coverage of all 436 4-digit unit groups.
- **CSO 4-digit ISCO coarseness.** The cube's "Type of Employee" axis is 3-bucket only, not 4-digit ISCO. Adapter emits one umbrella-bucket value per requested ISCO code; dashboard work (deferred) should surface the coarseness.

### Added — P3 (2026-05-11)
- Four ATS source adapters, each mirroring the Adzuna template (fail-isolated per slug, tenacity retries, `SourceFetchError` on persistent HTTP failures):
  - `src/jobpipe/sources/greenhouse.py` — `boards-api.greenhouse.io/v1/boards/<slug>/jobs`.
  - `src/jobpipe/sources/lever.py` — `api.lever.co/v0/postings/<slug>?mode=json`, handles both ms-epoch and ISO 8601 `createdAt`.
  - `src/jobpipe/sources/ashby.py` — `api.ashbyhq.com/posting-api/job-board/<slug>?includeCompensation=true`, parses structured compensation, annualises in-adapter (hourly × 2080, monthly × 12, etc.), drops mixed-currency comp to avoid spurious FX reinterpretation.
  - `src/jobpipe/sources/personio.py` — `<slug>.jobs.personio.de/xml`, parsed via `defusedxml` for entity-expansion safety; per-slug XML parse errors are logged + skipped.
- `src/jobpipe/sources/_companies.py` — shared helpers: `load_companies_file(path, ats_key)` (YAML loader) and `match_country(text, allowed_codes)` (loose ISO-2 derivation with `remote-europe` / `remote-worldwide` pseudo-code support).
- `defusedxml>=0.7` added as a top-level dependency for safe XML parsing.
- `config/companies/dublin_tech.yaml` populated with a starter set of 2–3 verified slugs per ATS (Greenhouse: intercom/stripe; Lever: palantir/mistral; Ashby: notion/linear/ramp; Personio: personio).
- Preset `config/runs/data_analyst_ireland.yaml` flips greenhouse/lever/ashby/personio to `enabled: true`.
- Tests: per-adapter MockTransport-driven suites (~12 tests each) + fixtures under `tests/fixtures/<adapter>/`. Each adapter file ≥92% line+branch coverage; overall coverage at 95.75%.

### Decided — P3 scope shifts (2026-05-11)
- **Remotive excluded** (see [DECISIONS.md ADR-009](DECISIONS.md#adr-009--remotive-excluded-from-ingest-sources)). Their ToS §8 prohibits redistribution and commercial database-building of job listings; the public-API README's attribution back-link advice does not override.
- **HN Algolia deferred to P4** alongside LLM-assisted comment parsing. "Who is hiring?" comments are free-text and benefit substantially from LLM-based title/salary extraction.

### Added — P2 (2026-05-11)
- `src/jobpipe/fx.py`: ECB daily reference-rate loader (`load_rates`) with 24h on-disk cache, plus the pure `convert_to_eur` step that rewrites the misnamed `salary_*_eur` columns into actual EUR. Covers all 19 Adzuna countries through `COUNTRY_CURRENCY`.
- `src/jobpipe/dedupe.py`: URL canonicalisation (lowercase host, strip `utm_*`/`gclid`/etc., drop trailing slash + fragment), sha1-based `posting_hash`, cross-source `cross_source` collapse.
- `src/jobpipe/normalise.run(raw, rates)`: real pipeline — FX → recompute `salary_annual_eur_p50` as post-FX midpoint → cross-source dedupe → strict-schema validation. Replaces the P0 passthrough; signature now requires a rates dict.
- `src/jobpipe/runner.py`: `find_latest_raw()` resolves the newest raw bundle by preset; `run_normalise()` orchestrates raw → enriched, preserving the run_id so raw↔enriched is trivially traceable.
- CLI `jobpipe normalise --preset … [--out-root … --verbose]` wired to `run_normalise`; explicit exit-code 2 on `PresetError` / `NoRawRunError`.
- `salary_imputed: bool` column on `PostingSchema`. Adzuna populates it from `salary_is_predicted` (the prior live run had ~60% imputed salaries — dashboards can now distinguish posted vs estimated).
- `PostingSchema.Config.strict = True` — P0/P1 scaffolding relaxation is now lifted; extra columns abort validation.
- Tests: `tests/test_fx.py`, `tests/test_dedupe.py`, `tests/test_normalise.py`. `tests/test_runner.py` gains `find_latest_raw` + end-to-end `run_normalise` cases.

### Fixed — P1 (2026-05-11)
- `AdzunaAdapter.fetch()` now collapses within-source duplicate `posting_id`s before returning. A single Adzuna posting can match multiple keywords ("data analyst" + "analytics engineer"), which previously broke `PostingSchema`'s uniqueness check during live runs. Cross-source dedupe remains P2 work.

### Added — P1 (2026-05-11)
- `AdzunaAdapter` (`src/jobpipe/sources/adzuna.py`): paginated fetch against `api.adzuna.com/v1/api/jobs/{country}/search/{page}`, normalises each result to a `PostingSchema` row, fail-isolates HTTP errors via `SourceFetchError`, retries transient failures via `tenacity`.
- `AdzunaConfig` extends `SourceConfig` with `results_per_page`, `max_pages`, `timeout_seconds`, `min_interval_hours`.
- Preset loader + runner (`src/jobpipe/runner.py`): `load_preset()` parses + validates run YAMLs (`PresetError` on malformed input), `fetch_sources()` fans out to enabled adapters with fail-isolation, `write_raw_parquet()` writes `data/raw/<preset_id>__<run_id>/postings_raw.parquet`. Zero rows across all enabled sources raises `EmptyRunError`.
- CLI `jobpipe fetch` wired to runner; `--verbose` flag for INFO logging; explicit exit code 2 on `PresetError` / `EmptyRunError`.
- `data_analyst_ireland.yaml` preset: adzuna enabled with country `gb` (English-language labour-market proxy; Ireland not served by Adzuna in 2026 — documented inline).
- Adzuna adapter tests (`tests/sources/test_adzuna.py`): synthetic JSON fixtures + `httpx.MockTransport` cover happy path, missing salary, paging short-circuit, missing credentials, HTTP 5xx error, empty response, `max_results` cap, and self-registration on import.
- Runner tests (`tests/test_runner.py`): preset loader error paths, adapter fan-out, fail-isolation, end-to-end Parquet write.

### Added — P0 (2026-05-11)
- Initial project scaffolding: `pyproject.toml`, `uv.lock`, Apache-2.0 licence, README, CONTRIBUTING, DECISIONS, NOTICE.
- Pluggable `SourceAdapter` and `BenchmarkAdapter` Protocols + registry decorators (no concrete adapters yet).
- Pandera schema skeletons (`PostingSchema`, `BenchmarkSchema`).
- Typer CLI skeleton (`jobpipe fetch | normalise | publish`).
- pydantic-settings configuration.
- v1 preset YAML (`config/runs/data_analyst_ireland.yaml`) with all sources disabled until per-phase activation.
- CI workflow (`.github/workflows/ci.yml`): ruff, mypy strict, pytest with coverage gate, licence audit.
- Pre-commit hooks (ruff, mypy, end-of-file fixer, check-yaml/toml).
- Architecture diagram in `docs/architecture.md`.
- Original Dagster-centric spec superseded by ADR-001.

[Unreleased]: https://github.com/USER/jobmarket_analyzer/compare/HEAD...HEAD
