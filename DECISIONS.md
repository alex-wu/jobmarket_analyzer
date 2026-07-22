# Architecture Decisions

ADR-lite. One entry per locked architectural decision. Format:

> **Status** · **Context** · **Decision** · **Consequences**

When a decision changes, mark the old entry `Superseded` (or `Amended by ADR-0NN`) and add a new entry; don't rewrite history.

---

## ADR-001 · Orchestration: GitHub Actions cron (not Dagster)

**Status:** Accepted, 2026-05-11.

**Context:** The project targets GitHub Pages — a static-only host — with a batch refresh cadence. An earlier spec prescribed Dagster.

**Decision:** A GitHub Actions cron workflow (`.github/workflows/refresh.yml`) orchestrates a plain Python CLI (`jobpipe fetch | normalise | publish`).

**Consequences:** ~1,000+ LoC saved; free for public repos; scheduling/retries/failure-handling come from Actions. Loses Dagster's UI and asset graph — acceptable for a small batch pipeline. Revisit if runs outgrow Actions limits (≥1 h runs, complex backfills).

---

## ADR-002 · Frontend: Observable Framework (not Evidence.dev, not Streamlit)

**Status:** Accepted, 2026-05-11.

**Context:** GitHub Pages serves static content only; the dashboard needs in-browser SQL, filters, and drill-downs.

**Decision:** Observable Framework — static build, DuckDB-WASM and SQL-in-markdown are native, Apache-2.0.

**Consequences:** Best-in-class browser-side interactivity. Evidence.dev was runner-up (more Python-native, weaker browser-side filtering); Streamlit/stlite rejected (Pyodide overhead, no DuckDB integration).

---

## ADR-003 · Ingestion: API-first, no JobSpy

**Status:** Accepted, 2026-05-11. **Amended by ADR-017** — active source set narrowed to Adzuna only.

**Context:** The original spec leaned on JobSpy (Indeed/LinkedIn scraping) for breadth; we run on GitHub Actions datacenter IPs, which those sites block.

**Decision:** API-first sources only; no browser-emulation scrapers.

**Consequences:** Smaller raw posting count, but reliable and ToS-clean. Uniform, lightweight HTTP+JSON adapters.

---

## ADR-004 · Storage + delivery: Parquet via GitHub Releases as CDN

**Status:** Accepted, 2026-05-11. **Amended by ADR-019** (per-preset tag naming) and **ADR-020** (`latest` is a recomputed accumulation, not a snapshot).

**Context:** The dashboard needs the latest dataset on every visit without paid storage or a bloated git history.

**Decision:** The pipeline uploads Parquet to two GitHub Releases per run: an immutable dated tag (audit history) and a moving `latest` tag re-clobbered each run. The Observable data loader fetches from the `latest` release at site build time.

**Consequences:** Zero infrastructure cost; public repos get unlimited bandwidth and 2 GB/asset. `manifest.json` records the run so the dashboard can detect staleness.

---

## ADR-005 · Licence: Apache-2.0 (not MIT)

**Status:** Accepted, 2026-05-11.

**Decision:** Apache-2.0 — explicit patent grant, standard in this space (DuckDB, Observable Framework, Pandera). `NOTICE.md` carries third-party attributions.

---

## ADR-006 · Occupation taxonomy: ESCO (ISCO-08), not O*NET/SOC

**Status:** Accepted, 2026-05-11.

**Context:** Postings need a stable occupation code; v1 geography is European — O*NET/SOC is US-only.

**Decision:** ESCO at the ISCO-08 4-digit level. Title → ISCO via rapidfuzz `token_set_ratio` (cutoff initially 88, later lowered to 85 after measuring real-data match rates); optional LLM fills gaps when enabled.

**Consequences:** ISCO-08 is the index used by Eurostat, OECD, and CSO — one join key serves any future benchmark source. ESCO's live API is flagged "to be replaced", so a static label snapshot is committed (see ADR-010). The snapshot redistributes ESCO labels, permitted by EUPL-1.2 with attribution (recorded in `NOTICE.md`).

---

## ADR-007 · LLM optional, openai-compatible

**Status:** Accepted, 2026-05-11. Narrowed by ADR-013 (client stubbed out of v1).

**Decision:** `LLMClient` wraps the `openai` SDK with configurable `base_url`/`api_key` — works with any OpenAI-compatible endpoint. The pipeline must materialise end-to-end with `LLM_ENABLED=false`; every transformation has a deterministic fallback (unresolved postings show "Unclassified").

---

## ADR-008 · Pluggable adapter pattern (sources + benchmarks)

**Status:** Accepted, 2026-05-11. **Amended by ADR-017** — only Adzuna is `enabled: true`; other adapters remain in tree, shelved via preset config.

**Context:** The codebase must generalise to other roles, geographies, and data sources without rework.

**Decision:** Two Protocol-based registries (`SourceAdapter`, `BenchmarkAdapter`) with `@register("name")` self-registration. Presets (`config/runs/*.yaml`) declare which adapters run and with what config.

**Consequences:** Adding a source/benchmark = one file + one test; adding a preset = one YAML file, zero code change. Enabling/disabling an adapter is a config-only flip — this is the shelf mechanism every later scope decision relies on. Forces a stable normalised schema (`PostingSchema`, `BenchmarkSchema`) as the contract.

---

## ADR-009 · Remotive excluded from ingest sources

**Status:** Accepted, 2026-05-11.

**Context:** Remotive's terms of use prohibit redistributing job listings and using the data to build a database — exactly what this project does (public dashboard + Parquet releases).

**Decision:** Exclude Remotive from v1; no adapter written.

**Consequences:** One source's worth of remote-EU volume unavailable. If explicit written permission changes the calculus, re-add via a superseding ADR (one new adapter file, per ADR-008).

---

## ADR-010 · ESCO label snapshot built by walking the ISCO concept tree

**Status:** Accepted, 2026-05-14.

**Context:** ADR-006 calls for a committed label snapshot. ESCO's public REST API caps every listing endpoint at offset 100 (returns empty results past it, no documented workaround), so flat pagination can't enumerate the ~3,000 occupations.

**Decision:** `scripts/build_esco_snapshot.py` walks the ISCO concept tree instead: BFS from the 10 major groups via `narrowerConcept` links, collecting each 4-digit group's preferred label plus its narrower-occupation titles. Produces `config/esco/isco08_labels.parquet` (~2,100 labels, all 436 unit groups, ~36 KB).

**Consequences:** Deterministic and complete; cheap to re-run when ESCO publishes a new version. Per-occupation alternative labels are not captured (would need ~3,000 extra calls); the narrower-title list is rich enough for fuzzy matching.

---

## ADR-011 · OECD SDMX adapter ships disabled (Cloudflare bot-protection)

**Status:** Accepted, 2026-05-14. Shelved by ADR-017.

**Context:** The live OECD SDMX endpoint returns HTTP 403 with a Cloudflare browser-challenge interstitial to anonymous clients, including GitHub Actions runners.

**Decision:** The adapter is built and fixture-tested but ships `enabled: false`. It detects the interstitial (HTML content-type) and returns an empty frame, so enabling it accidentally cannot break a run.

**Consequences:** Sets the precedent for gated upstreams: implement, fixture-test, ship disabled, document the unblock path (API key, CSV mirror, or fixed-egress proxy).

---

## ADR-012 · CSO PxStat 4-digit ISCO coarseness

**Status:** Accepted, 2026-05-14. Shelved by ADR-017.

**Context:** CSO Ireland's only quarterly earnings series (`EHQ03`) does not use ISCO-08 — its occupation axis collapses ISCO majors into three broad buckets.

**Decision:** The CSO adapter emits one benchmark row per requested ISCO code, mapped to the umbrella bucket via the leading digit, with the coarseness documented at every consumer.

**Consequences:** CSO rows support ballpark comparisons within a broad professional tier only. Eurostat SES offers 2-digit ISCO but at a ~4-year-lagged annual cadence — a different trade-off.

---

## ADR-013 · HN Algolia + LLM client descoped from v1

**Status:** Accepted, 2026-05-14.

**Context:** v1's narrative — pluggable adapters, deterministic ISCO path, free-tier deploy — needs no LLM. Carrying HN comment-scraping + a live LLM client adds API-key dependencies, reproducibility cost, and CI secrets.

**Decision:** Both out of scope for v1. `src/jobpipe/llm.py` stays as a documented stub (`classify_title_to_isco` + `LLMUnavailableError` are the locked contract); no LLM env vars required anywhere.

**Consequences:** CI runs `LLM_ENABLED=false` permanently for v1. ADR-007 is not superseded — it still describes the eventual shape; this ADR narrows what ships.

---

## ADR-014 · Local-only files excluded from the public repo

**Status:** Accepted, 2026-05-14.

**Decision:** Development-scaffolding artefacts (AI-assistant config, per-session working notes, superseded early specs) are gitignored. Load-bearing content lives in the public docs instead: contribution rules in `CONTRIBUTING.md`, module layout in `docs/architecture.md`, decision rationale here.

**Consequences:** The repo is self-documenting for contributors; forks bring their own tooling scaffolding rather than inheriting ours.

---

## ADR-015 · httpx credential redaction filter on the CLI logger

**Status:** Accepted, 2026-05-14. Extended 2026-07-21 (shared `redaction.py`, root-handler install — see CHANGELOG).

**Context:** Free-tier APIs pass credentials as URL query params (Adzuna: `app_id`/`app_key`). httpx logs full request URLs at INFO; Actions workflow logs are readable by anyone with repo access.

**Decision:** A `CredentialScrubFilter` rewrites known credential query-param values to `REDACTED` before any log record reaches a handler. Param names matched case-insensitively from a small extensible list.

**Consequences:** Central and adapter-agnostic. A defence layer, not a substitute for not logging URLs: `--verbose` stays opt-in and CI runs without it. Unit-tested in `tests/test_log_redaction.py`.

---

## ADR-016 · GitHub Pages deploy via `actions/deploy-pages` from the monorepo

**Status:** Accepted, 2026-05-14.

**Context:** Options: deploy from this repo via `actions/deploy-pages` (OIDC), push to a `gh-pages` branch, or a separate dashboard repo.

**Decision:** Monorepo + `actions/deploy-pages`. `pages.yml` builds the Observable site and deploys it; triggers are `workflow_run` after a successful refresh, `push` to `main` under `site/**`, and manual dispatch. Pages source = "GitHub Actions" (one-time setting, see `docs/github-setup.md`).

**Consequences:** Single CI ordering — refresh produces data, pages rebuilds against the latest release. The site reads data from Releases, never from repo paths, so the repo carries no binary data.

---

## ADR-017 · Scope cut to Adzuna-only post-v1 stabilisation

**Status:** Accepted, 2026-05-17. Amends ADR-003 and ADR-008.

**Context:** v1 shipped 5 source + 3 benchmark adapters. In production the ATS adapters returned zero rows, OECD was Cloudflare-gated (ADR-011), and CSO was ISCO-coarse (ADR-012). Wide-and-shallow multi-source starved iteration; Adzuna alone (19 countries, 250 free calls/day) leaves ample quota headroom for multi-country accumulation — a tighter, more honest story.

**Decision:** Adzuna is the only `enabled: true` source. ATS adapters, benchmark adapters, HN Algolia, and the LLM stub all remain in the codebase, shelved by preset config; no adapter code deleted. The active preset is `config/runs/data_analyst_eu.yaml`; it ships with `[gb, es]` — a deliberately small validation scope; widening the country list is a one-line YAML edit.

**Consequences:** No Ireland-resident postings (Adzuna doesn't serve `ie`); GB anchors the EU view. Schema unchanged; benchmark joins inert until reactivation. Multi-source returns via a superseding ADR once the Adzuna-only shape has proven stable end-to-end.

---

## ADR-018 · Weekly cadence + multi-country single-run

**Status:** Accepted, 2026-05-17.

**Context:** Cadence × country fan-out options: daily one-country rotation vs all-countries-per-run weekly. Weekly all-countries gives uniform per-country sampling and simpler cron-skip recovery, and weekly trend granularity is sufficient.

**Decision:** Weekly Monday 06:00 UTC cron plus `workflow_dispatch`; all preset countries fetched in one run.

**Consequences:** Per-run cost stays well inside Adzuna's free-tier quota. Closure-detection lag is one week. If per-country cost rises sharply, fall back to a multi-day rotation.

---

## ADR-019 · Multi-preset `latest-{preset_id}` release naming

**Status:** Accepted, 2026-05-17. Amends ADR-004.

**Context:** A single `latest` tag couples the pipeline to one preset; parallel presets would race on the same tag and asset names (`--clobber` matches by name).

**Decision:** Tags and assets are preset-scoped: moving tag `latest-{preset_id}`, dated tag `data-{preset_id}-YYYY-MM-DD`, asset `latest-{preset_id}.parquet`. Workflow concurrency groups by preset; `refresh.yml` uses a preset matrix.

**Consequences:** Presets run in parallel without artifact collision. The dashboard loader must eventually enumerate `latest-*` tags — until the switcher ships it pins one preset id. Moving-tag re-publishes wipe assets before upload (name-matched `--clobber` alone leaves orphans after layout changes).

---

## ADR-020 · Accumulated dataset via pure-function recompute

**Status:** Accepted, 2026-05-17. Amends ADR-004.

**Context:** Snapshot-only `latest` forecloses trend analysis. Two accumulation models: stateful append-merge (each run mutates the previous `latest` — corruption propagates forward) vs pure recompute from the immutable dated archive.

**Decision:** `latest-{preset_id}.parquet` is recomputed every run as a pure function of the dated archive within a config window (`publish.accumulate_window_days`, default 180): union the dated releases, group by `posting_id`, derive `first_seen_at`/`last_seen_at` from MIN/MAX `ingested_at`. Implemented in `src/jobpipe/duckdb_io.py:export_accumulated`.

**Consequences:**
- `latest` is always recomputable — a bad publish is fixed by re-running, no state drift.
- The window is a config value, not a destructive operation; archive retention is indefinite (public-repo release storage is effectively free at this volume).
- `last_seen_at` older than one cron interval signals upstream closure.
- Adds two nullable schema columns populated only in the accumulated artifact; `union_by_name` NULL-fills older archives, so schema bumps never require re-encoding history.

---

## ADR-021 · No per-country keyword translation table in v1

**Status:** Accepted, 2026-05-18.

**Context:** Hypothesis: non-English Adzuna markets would return locally-titled postings that match poorly against English-only ESCO labels, requiring per-country keyword translations.

**Decision:** No translation table. The first multi-country run measured ES ISCO match rate *above* GB (70.6% vs 53.5%) — Spanish tech postings are overwhelmingly English-titled. The real lever for match rate is ISCO label coverage (adding missing English titles like "Analytics Engineer" to the snapshot), not translation.

**Consequences:** One keyword list serves all countries. Re-open if widening to DE/FR/IT/PL surfaces materially lower match rates, or if the role family expands into more market-localised sectors.

---

## ADR-022 · PostingSchema v2 — persist 5 Adzuna fields + skills

**Status:** Accepted, 2026-05-18.

**Context:** The Adzuna response carries fields the adapter previously dropped (category label, contract type/time, truncated description, location hierarchy) that first-ask dashboard panels need. Separately, the dataset had no skill signal.

**Decision:** Schema version 2 adds six nullable columns: `adzuna_category`, `contract_type`, `contract_time`, `description` (length-capped), `location_area: list[str]`, and `skills: list[str]` (populated by ADR-023's tagger).

**Consequences:**
- No `isin` enums on `contract_type`/`contract_time` — Adzuna documents that undeclared values exist, and one novel value must not fail an unattended weekly run under strict-mode validation. Wire-tolerance beats strictness at the boundary.
- `union_by_name` in the accumulation step makes the bump forward-compatible with the existing archive.
- List columns round-trip from parquet as `numpy.ndarray`, not `list` — validation checks accept both.
- A drift-guard test fails the build if a future schema column is missing from the accumulation projection.

---

## ADR-023 · Skill enrichment via ESCO Pillar B + Aho-Corasick, scoped by preset `isco_focus`

**Status:** Accepted, 2026-05-18.

**Context:** The dashboard needs a skills view. ESCO's sister Pillar B (~13.9k skills) pairs naturally with the ISCO matcher already in place. ESCO's API pagination cap (ADR-010) rules out API enumeration, and the official CSV bundle is email-gated — not viable for unattended CI. The tabiya-tech open-dataset (github.com/tabiya-tech/tabiya-open-dataset) is the stable free public mirror, shipping ESCO v1.1.1 CSVs.

**Decision:** Commit a `config/esco/skills_labels.parquet` snapshot built from the tabiya mirror (`scripts/build_esco_skills_snapshot.py`); match lowercased preferred + alternative labels against `title + description` with an Aho-Corasick automaton (`pyahocorasick`); filter the dictionary to skills linked to the preset's `isco_focus` ISCO codes before building the automaton.

**Consequences:**
- A word-boundary post-filter rejects substring hits ("Java" inside "Javascript") — Aho-Corasick alone is substring-based.
- The `isco_focus` scoping cuts the dictionary from ~13.9k to ~900 skills for the data-analyst preset, eliminating sector-irrelevant noise. Switching presets is a YAML change; the committed snapshot stays the full Pillar B.
- English-only for v1 — the live markets post predominantly in English (ADR-021); revisit if new markets change that.
- tabiya is the supply-chain dependency for snapshot rebuilds; attribution in `NOTICE.md`.
- No new CLI subcommand or workflow step — the tagger runs inside `normalise`.

---

## ADR-024 · Filter state persistence via URL search params

**Status:** Accepted, 2026-05-19.

**Context:** Observable Framework navigates via full page loads, so `view()`-scoped filters reset on every page change; bookmarks and deep links to filtered views didn't exist.

**Decision:** Persist filter state in URL search params with vanilla DOM APIs: a `filterState.js` component reads params to seed filter defaults and writes non-default values back via `history.replaceState`; a small click listener injected from `observablehq.config.js` appends the current query string to internal navigation links at click time. Params equal to their default are omitted to keep URLs clean; unknown URL values fall back to defaults.

**Consequences:**
- Filtered views are shareable, bookmarkable, and survive navigation, refresh, and back-button.
- No localStorage — closing the tab drops state unless bookmarked; shareable links matter more for a public dashboard.
- No SPA migration: Framework's documented routing model stays intact.
- Chart queries stay on `DuckDBClient.of` + `db.query(string)`: Framework's fenced ```sql``` blocks parameter-bind `${...}` interpolations (an injection-safety feature), which cannot compose the WHERE-fragment strings our shared filters produce. Both patterns are first-class per the Observable docs; ours is the documented escape hatch for dynamic SQL.

---

## ADR-025 · PostingSchema v3 — drop dead-weight cols, ternary work_arrangement, /details/ off by default

**Status:** Accepted, 2026-05-29.

**Context:** A shape audit found four dead columns: `location_raw` (superseded by `location_area`), `region` (always NULL), `remote: bool` (conflates full-remote with hybrid), `year_month` (partition key with no consumer). Separately: float-math precision rot in salary midpoints, and a design question over whether work-arrangement tagging should fetch full posting bodies (Adzuna truncates `description` at ~500 chars; the full body needs one extra HTTP call per posting — measured at ~7pp coverage lift for ~50× wall-time).

**Decision:** Schema version 3:
1. Drop the four columns; older archives stay readable via `union_by_name` NULL-fill.
2. Add `work_arrangement: str` with `isin=["remote","hybrid","onsite"]`, nullable. The enum is safe here (unlike ADR-022's upstream fields) because the producer is our own deterministic tagger.
3. Round `salary_annual_eur_p50` to 2 decimals at the source.
4. The multilingual keyword tagger runs unconditionally against the truncated description (zero quota cost); the per-posting `/details/` fetcher is opt-in per preset YAML and ships **off** — the coverage lift doesn't justify the cost, and the endpoint is absent from Adzuna's public API spec.

**Consequences:**
- Tagger tiebreak: hybrid > remote > onsite (hybrid postings frequently also advertise "remote flexibility").
- Coverage is honest-but-thin (~15-18% classified); the dashboard shows the unclassified share explicitly as "unknown". Spanish keyword-dictionary expansion is the cheap next lift.
- Credential redaction extended to wrapped fetcher errors: exception messages that embed request URLs are scrubbed before logging, since logger-level filters (ADR-015) don't cover our own wrapping loggers. Regression-tested.

---

## ADR-026 · Dashboard v2 restructure — Europe choropleth, page consolidation, CSV export

**Status:** Accepted, 2026-07-20.

**Context:** Review of the previous dashboard surfaced structural issues: the weekly-cadence chart sat on the wrong page (with a near-duplicate elsewhere), country bar charts encoded geography less directly than a map, ESCO skills had no surface, and only one page had a data table (with no export).

**Decision:** Restructure holding a "vanilla Framework/Plot first" line:
1. Weekly cadence moves to Overview; the duplicate is deleted.
2. Geography becomes a single choropleth: a build-time loader prunes `world-atlas` to Europe (~539 kB, no committed binary, no network at build); stock `Plot.geo` with a fixed European bbox; a metric dropdown switches volume / median salary.
3. Arrangement charts get always-visible count + percentage labels via `Plot.text` (segments under 7% rely on tooltips).
4. Skills surfaced as a top-25 bar over `unnest(skills)`; a page-scoped role/title filter lives in the shared filter card.
5. CSV export on every data page via a shared `dataTable.js` (client-side Blob download of the current selection).
6. Colors stay built-in: Plot's default categorical scheme, `blues` for the two value-encoded surfaces.
7. `work_arrangement` joins the global filter card (URL-persisted like the rest, per ADR-024).

**Consequences:**
- Postings `country` codes are UPPERCASE ISO2; the choropleth join normalises case (a lowercase assumption initially rendered an empty map) and the smoke test asserts filled paths.
- A d3-cloud word-cloud experiment was cut on review — layout quality didn't justify deviating from stock Plot; no custom-viz deviations remain.
- The role filter is deliberately not URL-persisted and its options deliberately unfiltered (deriving them from other filters would create a reactive cycle).

---
