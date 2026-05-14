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

## ADR-009 · Remotive excluded from ingest sources

**Status:** Accepted, 2026-05-11.

**Context:** Remotive operates a public remote-jobs API (`https://remotive.com/api/remote-jobs`) and was originally scoped into P3 alongside the ATS adapters. The carry-over open question from the previous session was whether their ToS permits our use case (public OSS dashboard, redistributing the data via GitHub Releases as Parquet).

A pre-flight WebFetch of `https://remotive.com/terms-of-use` returned a Section 8 ("Prohibited Conduct") that, quoted verbatim, prohibits:

> "Copy, reproduce, redistribute, publish, or make available to any third party any job listings, company data, or other content from the Site, whether in whole or in part, by any means including but not limited to screenshots, downloads, email forwarding, or posting to social media, forums, messaging groups, or other platforms."

and:

> "Use job listings or data obtained through your subscription for any commercial purpose, including operating a competing service, reselling access, or building a database of job listings."

The README at `github.com/remotive-io/remote-jobs-api` advises attribution back-links as an etiquette norm, but that document is not the binding terms-of-use.

**Decision:** Exclude Remotive from v1. Do not write the adapter; keep the preset entry with `enabled: false` and a comment pointing here. The pluggable adapter pattern means re-adding it later is a single new file plus an ADR update.

**Consequences:**
- ~one source's worth of remote-EU posting volume is unavailable in v1.
- We avoid a defensible-but-borderline use of redistributed data on a public dashboard.
- If a future legal review or explicit written permission from Remotive changes the calculus, supersede this ADR rather than rewriting it.
- HN Algolia is the other "community" source originally scoped into P3; it is deferred to P4 alongside LLM-assisted comment parsing. That is a scope-shift, not an architectural decision, so it lives in `README.md` and the session log rather than as its own ADR.

---

## ADR-010 · ESCO label snapshot built by walking the ISCO concept tree

**Status:** Accepted, 2026-05-14.

**Context:** ADR-006 picked ESCO as the occupation taxonomy and called for committing a static `config/esco/isco08_labels.parquet` snapshot rather than depending on the live API at runtime (the EU flags the existing service as "to be replaced"). The P4 plan called for building the snapshot by paginating ESCO's `/api/search?type=occupation&full=true`.

A pre-flight probe of ESCO v1.2.1 (2025-12-10) confirmed two independent paginations broken at offset > 100:

- `/api/search?type=occupation&full=true&offset=100&limit=100` returns `total=2942`, `results=[]`.
- `/api/resource/concept?isInScheme=...&offset=100&limit=50` returns `total=3561`, `concepts=[]`.

Both ship 100 results at offset=0 then go empty. As of 2026-05-14 there is no documented workaround.

**Decision:** Build the snapshot by **walking the ISCO concept tree** instead of relying on flat pagination. Seed a BFS from the 10 ISCO major groups (`http://data.europa.eu/esco/isco/C0` through `…C9`), recurse via the `narrowerConcept` link on each node, and at every 4-digit leaf collect: the ISCO group's own preferred label (e.g. *Systems analysts → 2511*) plus every `narrowerOccupation.title` listed under it. Implementation: `scripts/build_esco_snapshot.py`. Runs in ~30 s, ~620 HTTP calls, produces a 36 KB parquet with 2 137 labels covering all 436 4-digit ISCO unit groups.

**Consequences:**
- Snapshot generation is deterministic and complete (no missed pages, no off-by-one), with a small enough request count to be rerun cheaply when ESCO publishes a new version.
- We do **not** capture each individual ESCO occupation's full `alternativeLabel.en` list (each concept's own alt-labels would require 2 942 additional GETs). The narrower-title list under each ISCO group is rich enough for fuzzy matching at the 88 cutoff — measured match rate on real data is the open question that drives the LLM-fallback PR.
- ESCO API contract may stabilise eventually. If `/api/search` pagination starts working again, prefer the flat-list approach — easier to maintain. Until then, keep the tree-walk.
- The snapshot redistributes ESCO labels (preferred + narrower titles), which is a fact `NOTICE.md` and the EUPL-1.2 attribution language need to reflect — ADR-006's "we redistribute only `(posting_id, isco_code)` join keys" is no longer strictly true. EUPL 1.2 explicitly permits redistribution of source material with attribution, so the snapshot is compliant; the NOTICE wording was tightened in this phase to match reality.

---

## ADR-011 · OECD SDMX adapter ships disabled (Cloudflare bot-protection)

**Status:** Accepted, 2026-05-14.

**Context:** P4 added three benchmark adapters (CSO PxStat, OECD SDMX, Eurostat SES). All three were implemented end-to-end with fixture-based unit tests passing. A pre-flight probe against the live OECD endpoint `https://sdmx.oecd.org/public/rest/dataflow/...` and `.../data/<flow>/<key>?format=jsondata` returned HTTP 403 with a Cloudflare *"Just a moment..."* HTML interstitial. This affects both anonymous local httpx requests and GitHub Actions runners — the upstream wants a real browser to solve a JavaScript challenge before letting traffic through.

The CSO and Eurostat endpoints have no such gating and respond cleanly to anonymous JSON requests.

**Decision:** The OECD adapter is **built and tested** but ships with `enabled: false` in `config/runs/data_analyst_ireland.yaml`. The adapter detects the Cloudflare interstitial by sniffing the response content-type (`text/html` instead of `application/json`) and returns an empty frame, so flipping it on accidentally cannot break the run. Workaround paths in priority order, for a follow-up PR:

1. Add `OECD_API_KEY` header (OECD offers a registered-developer programme with a paid tier — unverified whether the free option bypasses Cloudflare).
2. Switch the adapter to a CSV mirror via `data.oecd.org` / `data-explorer.oecd.org` exports if one publishes the same wage series.
3. Route the call through a fixed-egress proxy (e.g. a tiny Cloudflare Worker the project owns) so the request comes from a non-datacenter IP. Adds infrastructure cost — would violate the free-tier goal.

**Consequences:**
- Benchmark coverage on the dashboard is CSO (Ireland only) + Eurostat (Eurozone, ~4-year-lagged SES) until the workaround lands.
- The pluggable-adapter pattern means this is a config-only flip when ready; no code changes required to re-enable.
- Cloudflare gating may extend to other government APIs over time. This ADR sets the precedent: implement, fixture-test, ship disabled, document the unblock path.

---

## ADR-012 · CSO PxStat 4-digit ISCO coarseness

**Status:** Accepted, 2026-05-14.

**Context:** CSO Ireland's `EHQ03` PxStat cube (the only quarterly-cadence earnings series CSO publishes) does NOT use ISCO-08 occupation codes. Its occupation axis is the CSO-internal `C02397V02888` "Type of Employee" classification, which collapses ISCO majors into **three buckets**:

- `1` — Managers, professionals and associated professionals (ISCO majors 1–3)
- `2` — Clerical, sales and service employees (ISCO majors 4–5)
- `3` — Production, transport, craft and other manual workers (ISCO majors 6–9)

This was discovered during the P4 pre-flight probe — the original plan assumed CSO published by 4-digit ISCO like Eurostat does. It does not.

**Decision:** `src/jobpipe/benchmarks/cso.py` emits **one benchmark row per requested ISCO code**, mapped to the umbrella bucket via the leading digit. So a preset that asks for `isco_focus: [2511, 2521, 2423]` gets three benchmark rows — all with the same `median_eur` from bucket 1 (the managers+professionals umbrella). The umbrella-ness is documented in three places: the adapter's module docstring, `docs/adding-a-benchmark.md`, and the dashboard work (deferred) is responsible for surfacing it.

**Consequences:**
- CSO benchmark rows are usable for ballpark salary comparisons within a broad professional-grade tier, not for fine-grained ISCO-2511-vs-2521 differentiation.
- The Eurostat SES adapter does ship 2-digit ISCO breakdowns (`OC25`) but at a 4-year-lagged annual cadence — different trade-off.
- If CSO ever publishes a cube indexed by 4-digit ISCO (e.g. via a new National Employment Survey release), adapter the new cube's code in a new `dataset_code` config field; existing tests stay valid against the EHQ03 path.

---
