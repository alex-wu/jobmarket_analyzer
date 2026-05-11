# Architecture Decisions

ADR-lite. One entry per locked architectural decision. Format:

> **Status** · **Context** · **Decision** · **Consequences**

When a decision changes, mark the old entry `Superseded` and add a new entry; don't rewrite history.

---

## ADR-001 · Orchestration: GitHub Actions cron (not Dagster)

**Status:** Accepted, 2026-05-11.

**Context:** The project targets GitHub Pages — a static-only host. Refresh cadence is daily/weekly batch. The earlier `Project_Objectives.md` spec (now archived under `docs/history/`) prescribed Dagster.

**Decision:** Use a GitHub Actions cron workflow (`.github/workflows/refresh.yml`) as the orchestrator. The pipeline is a plain Python CLI (`jobpipe fetch | normalise | publish`).

**Consequences:**
- ~1,000+ LoC saved (no Dagster glue, asset definitions, resources, partitions).
- Free for public repos. No server to host.
- Retries, scheduling, and failure-handling come from GitHub Actions native features.
- Loses Dagster's UI and dependency graph — acceptable for a small batch pipeline.
- If we later outgrow this (≥1 hour runs, fan-out beyond GH Action's 6-hour limit, complex backfills), revisit.

---

## ADR-002 · Frontend: Observable Framework (not Evidence.dev, not Streamlit)

**Status:** Accepted, 2026-05-11.

**Context:** GitHub Pages serves static content only. The dashboard needs DuckDB queries, filters, drill-downs, and source-URL link-outs.

**Decision:** Observable Framework. Builds static HTML/JS at deploy time. DuckDB-WASM and SQL-in-markdown are native. Apache-2.0, active in 2025–2026.

**Consequences:**
- Best-in-class browser-side interactivity for our needs.
- JS learning curve (we are a Python-leaning project), but SQL blocks cover most logic.
- Evidence.dev was the runner-up: more Python-native, but weaker on browser-side filtering — most filters require build-time pre-compute.
- Streamlit (stlite) was rejected: Pyodide overhead (~10–30 MB), no DuckDB integration.

---

## ADR-003 · Ingestion: API-first, no JobSpy

**Status:** Accepted, 2026-05-11.

**Context:** Original spec leaned on JobSpy (Indeed, LinkedIn, Glassdoor, etc.) for breadth. We run on GitHub Actions datacenter IPs.

**Decision:** Exclude JobSpy and other browser-emulation scrapers. Use API-first sources only: Adzuna (Eurozone), Greenhouse / Lever / Ashby / Personio (public board APIs), Remotive (EU filter), Hacker News Algolia.

**Consequences:**
- Indeed and LinkedIn block GH Actions datacenter IPs — JobSpy would silently fail or return empty.
- Smaller raw posting count, but reliable and ToS-clean.
- Adzuna doesn't cover Ireland directly — gap filled by ATS adapters and Remotive.
- Source adapters are uniform and lightweight (HTTP + JSON), keeping ~1,200 LoC target realistic.

---

## ADR-004 · Storage + delivery: Parquet via GitHub Releases as CDN

**Status:** Accepted, 2026-05-11.

**Context:** The dashboard needs the latest dataset on every visit. Options: commit Parquet to repo (bloats history), Cloudflare R2 / S3 (paid account), GitHub Releases (free, public, unlimited bandwidth).

**Decision:** Pipeline writes partitioned Parquet under `data/publish/`. The `refresh.yml` workflow uploads to two GitHub Releases per run: a dated tag `data-YYYY-MM-DD` (audit history) and a moving `latest` tag (re-clobbered each run). The Observable data loader fetches from the `latest` release URL at site build time.

**Consequences:**
- Zero infrastructure cost.
- Public repos = unlimited bandwidth, 2 GB per asset, no rate limit.
- Daily volume is small (≤ ~5 MB / day for v1 scope), so retention is cheap.
- `gh release upload latest --clobber` is the upload pattern; manifest.json records the run_id so the dashboard can detect staleness.

---

## ADR-005 · Licence: Apache-2.0 (not MIT)

**Status:** Accepted, 2026-05-11.

**Context:** The project is a public OSS portfolio piece. Contributors and forkers need a permissive licence.

**Decision:** Apache-2.0.

**Consequences:**
- Explicit patent grant (MIT has none). Lower legal risk for downstream users.
- Standard for analytics tooling in this space (DuckDB, Observable Framework, Pandera all Apache-2.0).
- Requires `NOTICE.md` for third-party attributions — we maintain one anyway for Remotive and ESCO.

---

## ADR-006 · Occupation taxonomy: ESCO (ISCO-08), not O*NET/SOC

**Status:** Accepted, 2026-05-11.

**Context:** Postings need a stable occupation code to join against benchmarks. v1 geo is Eurozone — O*NET/SOC is US-only.

**Decision:** ESCO (European Skills, Competences, Qualifications and Occupations) at the ISCO-08 4-digit code level. Title → ISCO via `rapidfuzz.token_set_ratio` ≥ 88; LLM fills gaps when `LLM_ENABLED=true`.

**Consequences:**
- EUPL 1.2 licence on the taxonomy itself. We redistribute only `(posting_id, isco_code)` join keys, not ESCO labels, so we stay clear of EUPL copyleft scope.
- ESCO's local API is flagged "to be replaced" — mitigation: commit a static `config/esco/isco08_labels.parquet` snapshot, refresh quarterly via a manual workflow.
- ISCO-08 is also the index used by Eurostat, OECD, and CSO — same join key works for all three benchmark sources.

---

## ADR-007 · LLM optional, openai-compatible

**Status:** Accepted, 2026-05-11.

**Context:** LLM can fill gaps deterministic code can't (salary regex misses, ISCO fuzzy-match ambiguities). But we don't want a hard dependency on a paid API.

**Decision:** `LLMClient` wraps the `openai` SDK with `base_url` and `api_key` from settings. Works with OpenAI, Ollama, vLLM, LM Studio, or any OpenAI-compatible endpoint. Pipeline must materialise end-to-end with `LLM_ENABLED=false`.

**Consequences:**
- Every transformation has a deterministic fallback (`isco_match_method = none` for unresolved postings; dashboard shows "Unclassified").
- The manifest surfaces "LLM-assisted ISCO matches: X" so reviewers can see both paths work.
- CI runs with `LLM_ENABLED=false` and uses `pytest-httpserver` for fake-endpoint LLM tests.

---

## ADR-008 · Pluggable adapter pattern (sources + benchmarks)

**Status:** Accepted, 2026-05-11.

**Context:** v1 focuses on data-analyst roles in Ireland, but the codebase must generalise to other roles, geographies, and data sources without rework.

**Decision:** Two Protocol-based registries:
- `SourceAdapter`: `fetch(config: SourceConfig) -> pd.DataFrame` conforming to `PostingSchema`.
- `BenchmarkAdapter`: `fetch(config: BenchmarkConfig) -> pd.DataFrame` conforming to `BenchmarkSchema`.

Adapters self-register via a `@register("name")` decorator. Presets (`config/runs/*.yaml`) declare which adapters run and with what config.

**Consequences:**
- Adding a new source or benchmark = one file + one cassette + one test. No changes to the runner, normalise step, or dashboard.
- Adding a new preset = one YAML file. Zero code change.
- Forces a stable normalised schema (`PostingSchema`, `BenchmarkSchema`) as the contract.

---
