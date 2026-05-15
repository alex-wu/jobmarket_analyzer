# Open questions

Single source of truth for what the project knows it hasn't solved yet. ADRs in [DECISIONS.md](../DECISIONS.md) document locked decisions; this file tracks the loose ends.

Items move between sections as they're resolved. When an item closes, leave a one-line entry under **Resolved** with the ADR or session-log reference so the audit trail survives.

---

## Resolved

- **P6 dashboard rebuild + P7 GitHub Pages deploy** — Single-page BI canvas live at <https://alex-wu.github.io/jobmarket_analyzer/>. Three feature commits on `main` (`dc4c46f`, `7ea1f6e`, `40fb37a`). Operations runbook at [`docs/operations.md`](operations.md). Comprehensive context for the next agent: [`docs/sessions/2026-05-15-p7-shipped-handover.md`](sessions/2026-05-15-p7-shipped-handover.md).
- **Adzuna free tier capacity** — `max_pages=5 × results_per_page=50 = 250` per fetch, with `min_interval_hours=24` as the safety knob. Lived at 499 rows across two keywords in P1's live run without tripping the limit (P1 acceptance).
- **Remotive ToS** — Excluded entirely. ToS §8 prohibits redistribution + commercial database-building; attribution back-links don't override. See [ADR-009](../DECISIONS.md#adr-009--remotive-excluded-from-ingest-sources).
- **ESCO live API pagination** — `/api/search` and `/api/resource/concept?isInScheme=...` both cap at offset=100 as of v1.2.1. Workaround: walk the ISCO concept tree to build a static snapshot. See [ADR-010](../DECISIONS.md#adr-010--esco-label-snapshot-built-by-walking-the-isco-concept-tree).
- **HN Algolia + LLM client** — Descoped from v1. Contract stays as a stub for the post-v1 follow-up. See [ADR-013](../DECISIONS.md#adr-013--hn-algolia--llm-client-descoped-from-v1).
- **Local-only files (`CLAUDE.md`, `.claude/`)** — Untracked + gitignored. See [ADR-014](../DECISIONS.md#adr-014--local-only-files-excluded-from-the-public-repo).
- **`--verbose` httpx credential leak** — Centralised scrub filter on the `httpx`/`httpcore` loggers; tested in `tests/test_log_redaction.py`. See [ADR-015](../DECISIONS.md#adr-015--httpx-credential-redaction-filter-on-the-cli-logger).
- **GitHub Pages deploy strategy** — Monorepo with `site/`, `actions/deploy-pages`, Pages source = "GitHub Actions". See [ADR-016](../DECISIONS.md#adr-016--github-pages-deploy-via-actionsdeploy-pages-from-the-monorepo) and the manual checklist in [`docs/github-setup.md`](github-setup.md).
- **Publish-stage partition shape** — `partition_by: []` (single flat `postings.parquet` per release) chosen over hive-on-flat-release. GitHub Releases is a flat-asset namespace; hive partitioning was stripping `country` from the parquet payload (it lives in the directory path, lost on flatten). Single flat file keeps `country` + `year_month` as real columns. ADR-004's "hive partitioning" wording deviates here at the config layer; ADR text unchanged. Decision in P5 close-out session, 2026-05-15.

---

## Still open — owned by a future phase

### Dashboard cold-load performance (owned by P8)

DuckDB-WASM ships as **7.2 MB compressed (~36 MB uncompressed)** in `dist/_npm/@duckdb/`. The dataset it queries is **23 KB compressed (~55 KB uncompressed)** — the WASM module is ~310× the data. Every cold visit downloads it; `Cache-Control: max-age=600` only covers repeats within 10 minutes. Cold-load is dominated by WASM init (1-2 s) + nine sequential SQL cells against the in-browser engine.

Strategy doc [`docs/dashboard_strategy.md`](dashboard_strategy.md) §2 principle 8 ("SQL is the single source of truth for filter logic") was correct intent at the wrong scale. For ≤1000 rows and fixed aggregations, JS `d3.rollup` does the same work in <1 ms with zero WASM dependency.

Recommended path (full scoping in [`docs/sessions/2026-05-15-p7-shipped-handover.md`](sessions/2026-05-15-p7-shipped-handover.md) §3):

- **Path C — Hybrid pre-bake + client-side filter.** Static aggregates as JSON loaders; raw 504-row JSON for filter-dependent cells; `d3.rollup` does the math in JS. Cold load <500 ms; filter response <50 ms. ~1 day rework. **Ships ADR-017** formally superseding the strategy doc principle.

Other paths rejected: (A) service worker cache the 7 MB WASM — half-measure; (B) full data-loader rewrite without raw-rows JSON — loses filter interactivity.

### CI/CD modernisation backlog (owned by P9)

Surfaced from `pages.yml` / `refresh.yml` / `ci.yml` run annotations on 2026-05-15:

- **Node.js 20 actions deprecated.** GitHub forces Node 24 from 2026-06-02 (hard deadline). Bump `actions/checkout`, `actions/setup-node`, `actions/configure-pages`, `actions/upload-pages-artifact`, `actions/deploy-pages`, `astral-sh/setup-uv` to their Node-24 versions.
- **`puppeteer@23.11.1` unsupported** (< 24.15.0). Bumping clears 4 transitive deprecation warnings (`inflight`, `glob@8`, `glob@10`, `whatwg-encoding`).
- **No `.github/dependabot.yml`.** Add 3-ecosystem config (npm in `site/`, pip via `uv.lock`, github-actions at root).
- **No branch protection on `main`.** Anyone with write access pushes direct. Add: required PR + 1 review + green CI/pages checks.
- **No CodeQL.** Free on public repos; add `.github/workflows/codeql.yml`.

### Pipeline coverage regressions (owned by P10)

Run `25913215989` (2026-05-15 10:32 UTC) logged zero-row returns from:

- ATS adapters: Lever, Ashby, Personio
- Benchmark adapters: CSO PxStat, Eurostat SES

If this has been silent on every cron since P5, the benchmark overlay claim on the dashboard ("salary vs official wage statistics") is currently unbacked. Investigation: replay the most recent `refresh.yml` log; spot-check each company's careers endpoint + each statistics-agency SDMX/PxStat path manually. Each adapter either gets fixed or marked disabled with an ADR (parallel to ADR-011 for OECD).

Also: `src/jobpipe/runner.py:116` emits a `pandas` FutureWarning about empty-frame concatenation that will become an error in a future pandas release. Pre-filter empty frames before `pd.concat`.

### OECD SDMX unblock (no current owner)

`sdmx.oecd.org` returns 403 + a Cloudflare "Just a moment..." interstitial to anonymous httpx requests. The adapter ships disabled per [ADR-011](../DECISIONS.md#adr-011--oecd-sdmx-adapter-ships-disabled-cloudflare-bot-protection). Unblock paths in priority order:

1. OECD-issued API key header (registered developer programme — unverified whether the free option bypasses Cloudflare).
2. Switch the adapter to a CSV mirror via `data.oecd.org` / `data-explorer.oecd.org` if one publishes the same wage series.
3. Route through a fixed-egress proxy (Cloudflare Worker etc.). Adds infrastructure cost — would violate the free-tier goal.

Until one of those lands, benchmark coverage is CSO (Ireland) + Eurostat (Eurozone, 4-year-lagged SES).

### P6 dashboard decisions

These all require visual inspection of real data and are deferred until `site/` exists.

- **Adzuna posting recency.** Live P1 returned `posted_at` up to a year old. Decide: filter at ingest, surface an age column on the dashboard, or show a freshness badge per posting.
- **`salary_min_eur == 0` rows.** Adzuna emits a small non-zero count of zero-floored salaries. Decide: surface or hide.
- **CSO 4-digit ISCO coarseness.** [ADR-012](../DECISIONS.md#adr-012--cso-pxstat-4-digit-isco-coarseness) documents that CSO's `EHQ03` cube maps to a 3-bucket umbrella. The dashboard must not present CSO bucket-1 numbers as if they were ISCO-2511-specific. UI decision: label, tooltip, or row-level disclaimer.
- **Cross-source dedupe efficacy on the live mix.** Same job often appears on the company's Greenhouse and on Adzuna. Measure overlap once we have a full daily run.
- **Cross-day delta surfacing.** None of the source upstreams expose an incremental API, so every refresh fetches the full current set (see [`docs/architecture.md`](architecture.md#source-api-delta-semantics) for per-source detail). `posting_id` is stable, so the same posting reappears every day until it's removed upstream; `posted_at` is the upstream-reported create/update timestamp; `ingested_at` advances. P6 decision: present each daily release standalone (simplest, matches the publish model), compute `first_seen_at` by joining historical releases at build time (better UX, more loader logic), or flag "new today" by diffing against the previous `data-YYYY-MM-DD` release (cheaper, only needs the prior day).

### ISCO live-match-rate measurement (post-first-Actions-run)

Run 2 of `refresh.yml` (2026-05-15, n=504, cutoff=88) measured a **55.75% fuzzy match rate** (281 fuzzy / 223 none) — below the 60% ADR-013 threshold by ~4 percentage points.

Action taken this session: lowered `DEFAULT_SCORE_CUTOFF` in `src/jobpipe/isco/tagger.py` from 88 → 85 to capture more borderline fuzzy hits. ADR-006 was not amended (the constant is in the code, not the ADR text); the deviation is recorded here and revisited after Run 3+.

A local re-run on the previous raw bundle (n=493 after recency filter) yielded fuzzy=269 / none=224 (54.56%) — the rate moved only marginally. The cutoff lowering may not be enough on its own; Run 3 (fresh data with recency floor at the source) is the next data point.

If Run 3+ stays below 60%, the LLM-fallback re-scope discussion (currently descoped via ADR-013) becomes load-bearing.

### Recency-filter coverage on non-Adzuna sources

`normalise.run()` now applies a canonical `since_days=180` floor pre-dedupe (per preset `normalise.since_days`), and the Adzuna adapter passes `max_days_old=180` as a bandwidth optimisation. ATS sources (Greenhouse/Lever/Ashby/Personio) self-prune via company removal, so the floor is rarely binding for them — but the filter still applies uniformly. Verify on Run 3 that no ATS source ever serves a posting older than 180 days; if so, the assumption holds. Otherwise consider an adapter-level optimisation (none of these expose an "updatedSince" param on the free tier today).
