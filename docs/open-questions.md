# Open questions

Single source of truth for what the project knows it hasn't solved yet. ADRs in [DECISIONS.md](../DECISIONS.md) document locked decisions; this file tracks the loose ends.

Items move between sections as they're resolved. When an item closes, leave a one-line entry under **Resolved** with the ADR or session-log reference so the audit trail survives.

---

## Next phase — pipeline automation verification (branch `feat/pipeline-automation` → `feat/pipeline-hardening`, 2026-07-21 review)

Goal: prove the weekly GitHub Actions pipeline is *correct*, not just green. A 4-track review on 2026-07-21 (extraction code, docs-vs-reality, automation readiness, Adzuna upstream API/ToS) established: the automation is code-complete and has run green weekly since 2026-06-08; secrets/Pages/permissions are already configured in the repo. Findings and hardening landed on `feat/pipeline-hardening`.

**Done 2026-07-21** (see Resolved): docs-vs-reality cleanup (12 files); credential-leak fix in `adzuna.py` error wrapping + traceback-scrubbing filter on root handlers; retry restructured (was dead code — conversion to `SourceFetchError` inside the retried function hid httpx errors from tenacity) and restricted to 5xx/429/transport; `max_results` truncation warning; NaT `posted_at` quarantine; `accumulated_row_count` manifest annotation; `refresh.yml` failure-alert issue step.

**Still open in this phase:**

- **Adzuna ToS clarity** — upstream ToS restricts republishing aggregates ("vacancy counts, average salaries etc") as "ongoing work" by an organisation without written consent; personal research is permitted with attribution ("The Adzuna API" + link). Action: add the attribution line to the dashboard footer; consider emailing Adzuna for written consent given the fork-friendly public-OSS posture. (2026-07-21 upstream research, official ToS page.)
- **`/details/{id}` endpoint is undocumented upstream** — absent from Adzuna's official OpenAPI spec (only `/search`, `/categories`, `/histogram`, `/history`, `/geodata`, `/top_companies`, `/version`). The WA fetcher works today but could vanish without notice; one more reason it stays opt-in.
- **Artifact correctness gate** — validate the published `latest-{preset_id}.parquet` + `manifest.json` after each cron: schema_version matches, row_count sane vs prior week (alert on >50% drop), pandera-validate the published parquet, work_arrangement/skills coverage within expected bands. (`accumulated_row_count` now in manifest as the input signal.)
- **Gate `min_total_rows: 80` calibration** — still the documented guess; ground it against the fresh-delta row counts of the 7 published weekly manifests.
- **Accumulation window audit** — `export_accumulated()` unions 180 days of dated releases; verify dated-release retention and that the union actually dedupes as intended on real multi-week data (first_seen_at/last_seen_at drift). 7 dated releases now exist (2026-06-08 … 2026-07-20) — enough real data to audit.
- **`raw_payload` in the public asset** — full Adzuna JSON per row ships in `latest-*.parquet`. Bloat + ToS surface. Decide keep/drop.
- **PR-gate smoke** (carried over) — path-filtered smoke on PRs touching `site/**`; would have caught the choropleth-join bug pre-merge.
- Carried context: preset switcher still queued (loader hardcodes `data_analyst_eu`; docs now say so honestly); ES keyword dictionary still thin (ES work_arrangement 88% NULL).

## Resolved

- **2026-07-21 comprehensive review + hardening.** Four-track review (extraction/processing code, docs-vs-reality, CI automation readiness, Adzuna upstream API + ToS from the official OpenAPI spec). Docs cleanup merged to `main` via PR #32 (`769b43b`): required-secrets truth, phantom `presets.json` generator removed from 5 docs, gb+es scope, NOTICE attributions (Remotive/HN removed; ESCO skills v1.1.1 via tabiya-tech added), fixture test pattern, Node 24. Code hardening on `feat/pipeline-hardening`: (1) **credential leak closed** — `adzuna.py` wrapped httpx errors verbatim (URL embeds `app_id`/`app_key`) and `logger.exception` on the `jobpipe.runner` logger bypassed the ADR-015 filter; now scrubbed at the wrap via shared `jobpipe/redaction.py`, and `CredentialScrubFilter` scrubs exception tracebacks + installs on root handlers; (2) **retry was dead code** — `_get_page` converted to `SourceFetchError` inside the retried function so tenacity's `retry_if_exception_type(httpx.HTTPError)` never matched; split into `_get_page_raw` (retried, 5xx/429/transport only via `jobpipe/httputil.py`) + wrapping caller; WA fetcher no longer retries 404 3×; (3) `max_results` truncation now warns with skipped (country, keyword) pairs; (4) NaT `posted_at` rows quarantined with warning instead of aborting the run; (5) manifest gains `accumulated_row_count` / `accumulate_window_days` (fresh-delta `row_count` semantics unchanged — that's the gate's calibration target); (6) `refresh.yml` files/bumps a GitHub issue on failure (`issues: write`). Ops verification: `ADZUNA_APP_ID`/`ADZUNA_APP_KEY` secrets set 2026-05-15, Pages `build_type: workflow`, Actions default permissions `write`, refresh cron green weekly 2026-06-08 → 2026-07-20.
- **Failure loudness** — resolved 2026-07-21: `refresh.yml` "Alert on failure" step opens (or comments on) a `refresh failed: preset {id}` issue on any red run.
- **Pages rebuild coupling** — verified 2026-07-21: `pages.yml` `workflow_run` trigger on `refresh` completion is present and the deployed dashboard tracks weekly data.
- **Schema v3 merged to `main` 2026-06-04 (PR #19, squash, `--admin`).** [[project-schema-v3-landed-2026-05-29]] shipped to `main` as squashed commit `2601053`. Included a follow-up FX fix (`convert_to_eur` now rounds EUR salary cols to 2dp — source `_recompute_p50` rounding had missed the post-conversion path) and four waves of CI lint/format/mypy fixes the local pytest run did not surface (dead `is_remote` in shelved ATS adapters, `noqa RUF001` on intentional en-dash regex, ruff format, mypy `Series|None` narrowing in `tagger.py`). Lesson: run the FULL gate locally before PR push — `ruff check . && ruff format --check && mypy --strict src/jobpipe && pytest -q`. ~~Note: no published parquet is v3 yet~~ **Resolved 2026-07-20:** the weekly cron has published schema-v3 `latest-data_analyst_eu` assets (verified: manifest `schema_version: "3"`, 906 accumulated rows, generated 2026-07-20T08:57Z; refresh runs green weekly since 06-29). Handover: `docs/sessions/2026-06-04-schema-v3-merge-dashboard-bootstrap.md`.
- **Schema v3 cleanup 2026-05-29 (ADR-025).** Dropped `location_raw` / `region` / `remote: bool` / `year_month` — dead-weight or redundant columns. Added `work_arrangement: str` (remote / hybrid / onsite / NULL) populated by a new multilingual keyword tagger at `src/jobpipe/work_arrangement/`. Salary `salary_annual_eur_p50` rounded to 2 decimals at the source. Manifest bumped to schema_version `"3"`. The Adzuna `/v1/api/jobs/{country}/details/{id}` fetcher exists but is **off by default** — verified empirically that full-body inference lifts coverage ~7 percentage points (22% vs ~15%) at ~50× wall-time cost. The tagger always runs against the truncated `description` already in the frame at no quota cost. Closes "P12 remaining — remote derivation" (work_arrangement supersedes the boolean signal). Closes "salary_min_eur == 0" (the rounding side-effect makes zero-floored vs non-zero entries visually identical; UI decision still open but no longer driven by float noise). New opens added below.

- **Filter state persistence across pages 2026-05-19.** Shipped via URL search params (`?country=es&isco=2&salary_lo=10000&...`) + a tiny click-time anchor rewriter in `observablehq.config.js` `head:` script that appends `location.search` to internal sidebar + footer links at navigation time. `replaceState` (not `pushState`) so filter twiddling doesn't pollute back-button history. Smoke extended from 1 page → 5 pages. Also closes the **preset switcher state persistence** P13 follow-up (was URL vs localStorage; URL params chosen, applies to all filters including preset). Caveat: an earlier session iteration attempted a frontmatter `sql:` migration; reverted after discovering fenced `sql id=` blocks parameter-bind `${...}` interpolations, breaking SQL-fragment composition (see `pitfall-framework-sql-fenced-block-param-binding` memory). The shipped pattern keeps `DuckDBClient.of` for dynamic queries — both patterns are first-class per Observable docs. See [ADR-024](../DECISIONS.md#adr-024--filter-state-persistence-via-url-search-params).
- **Scope pivot 2026-05-17 — Adzuna-only + multi-preset accumulation.** ADR-017 (scope cut), ADR-018 (weekly cadence), ADR-019 (multi-preset `latest-{preset_id}` naming), ADR-020 (pure-function accumulation). Closes several previously-open items below:
  - "Dashboard cold-load performance (P8)" — folded into P13 as a forcing function of ADR-020 (accumulated parquet at 150-250 MB forces build-time loaders).
  - "Pipeline coverage regressions (P10)" — zero-row ATS adapters closed by descope. Code remains in tree, shelved by preset config.
  - "OECD SDMX unblock" — closed by descope. Benchmark adapters shelved.
  - "Adzuna posting recency" (P6 dashboard decision) — `max_days_old: 180` + `since_days: 180` carried over; accumulation window matches.
  - "CSO 4-digit ISCO coarseness" — moot; CSO shelved.
  - "Cross-source dedupe efficacy on live mix" — moot; only Adzuna sources postings.
  - "Cross-day delta surfacing" — resolved by accumulation: `first_seen_at` / `last_seen_at` derived per posting (ADR-020).
  Implementation = P13. Comprehensive handover: see `docs/sessions/2026-05-17-adzuna-only-scope-pivot-handover.md` (local only per ADR-014).
- **P9 CI/CD modernisation** — Shipped 2026-05-15 across 8 PRs (`#2` umbrella, `#3-#5/#7` first Dependabot wave, `#6` closed as ghost version, `#8` doc fix, `#9` Scorecard tag pin). Active automation: CodeQL (Python + JS matrix), Dependabot weekly grouped (npm + pip + actions), OpenSSF Scorecard + README badges, actionlint, Dependabot auto-merge for patch+minor. Light branch protection on `main` (required checks = `test` + `analyze (python|javascript)`; no PR-review wall; `delete_branch_on_merge: true`). Comprehensive handover: [`docs/sessions/2026-05-15-p9-shipped-handover.md`](sessions/2026-05-15-p9-shipped-handover.md). Reference: [`docs/ci-cd-practices.md`](ci-cd-practices.md). Deferred design (now ADR-020): [`docs/data-history-design.md`](data-history-design.md) for weekly cron + 6-month accumulation.
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

### Schema-v3 follow-ups (post-ADR-025)

- **Spanish keyword dictionary thin** — empirical Run on 2026-05-29 showed ES 88% NULL vs GB 72% NULL for `work_arrangement`. Quick win: add `100% remoto`, `presencial obligatorio`, `dos días en la oficina`, `oficina + casa` variants. ~30 min job; test cases in `tests/work_arrangement/test_tagger.py` already cover the table-driven shape.
- **`/details/{id}` fetcher reactivation criteria** — currently off in `data_analyst_eu.yaml`. Re-enable when: (1) Spanish dictionary expansion plateaus AND (2) dashboard demonstrates demand for `work_arrangement` coverage above ~20%. Cost discipline lives in the `max_details_calls_per_run` cap (currently 1500) — keep it set even when toggled on so a wave of fresh postings can't blow weekly quota.
- **Dashboard surface for `work_arrangement`** — DONE 2026-07-20 on branch `feat/dashboard-v2-restructure` (ADR-026): dedicated `/arrangement` page (coverage caveat + 3 charts with always-visible count/percent labels) + `work_arrangement` column in every page's Filtered-postings export. The dominant NULL bucket is shown explicitly as `unknown`. Local sample-data strategy resolved by the whole-`/data/`-gitignore: the sample is swapped locally per run (2026-07-20 fresh v3 run in place); the first post-merge cron publish makes the release asset v3.
- **Role/title filter is skills-page-scoped** (ADR-026) — rendered inside the shared filter card via the `extras` slot, but not URL-persisted and not cross-page. Revisit only if cross-page title analysis becomes a real workflow.
- **Cross-language tagger noise** — the tagger always combines country language + English. Some English `\b`-anchored matches may fire on Spanish text that incidentally contains English words ("Remote, Spain" in a recruiter posting). Low frequency, audit when we add more EU countries.

### Scope-pivot follow-ups (P13)

New open questions surfaced by ADR-017..020. To resolve during P13 implementation:

- ~~**Preset switcher state persistence.**~~ Resolved 2026-05-19 — URL params chosen and shipped for ALL filters (country, ISCO, salary, dates, preset). See Resolved.
- **First-run backfill window.** Pre-pivot dated releases (`data-2026-05-XX`) exist for the legacy `data_analyst_ireland` preset (different country mix, GB-only). Include them in the first `data_analyst_eu` accumulation? Pre-pivot rows lack the new `country` mix but `posting_id` / `ingested_at` are sound — including them backfills GB history at the cost of mixed-preset provenance.
- **Gate `min_total_rows` after pivot.** Set to `200` in the handover spec as a guess. Revise after first 1-2 real runs ground a baseline. May want per-country sub-thresholds (`min_rows_per_country: 20`) if a single-country failure should fail the gate.
- **Per-preset Pages deploy ordering.** `pages.yml` fires once per `refresh.yml` matrix job completion. If two presets finish 30 seconds apart, Pages may rebuild twice in quick succession. Acceptable today; revisit if it becomes annoying. Possible fix: debounce in `pages.yml` via `concurrency: pages` no-cancel.
- **ADR-017 reactivation criteria measurability.** "Multi-country unified merge proven stable end-to-end" — define stability concretely (one full 180-day accumulation cycle without manual intervention? Gate green for N consecutive runs? Some other measure?).
- **Closure-detection lag under weekly cadence.** `last_seen_at < generated_at - 7d` is the right predicate, but the dashboard needs to communicate that "closed yesterday" cannot be detected until next Monday. UX wording question.

### Dashboard cold-load performance — CLOSED, folded into P13

The DuckDB-WASM 7.2 MB / 23 KB dataset mismatch is **strictly worse** post-pivot (accumulated parquet → 150-250 MB). ADR-020 makes build-time data loaders + client-side `d3.rollup` mandatory, not optional. Path C from the previous handover is the implementation route. Full scoping was in `docs/sessions/2026-05-15-p7-shipped-handover.md` §3 — preserved for reference, executed in P13.

### CI/CD follow-ups (residual from P9)

P9 shipped the modernisation; these are residual items deliberately not closed:

- ~~Branch protection `strict: true` → `false`~~ **applied end of P9 session.** Dependabot waves no longer bottleneck on sequential rebase. Payload archived in P9 handover §6.
- **4 transitive npm warnings still present.** Diagnosed in P9 as Observable Framework's deps (`@rollup/plugin-commonjs@25.0.8` + `jsdom@23.2.0`), not puppeteer or rimraf. Not actionable until Observable Framework upgrades its pins. Dependabot will surface the PR.
- **`puppeteer` 25.x not yet on npm** despite Dependabot proposing 25.0.2 (closed as PR #6). Re-watch when 25.x publishes — the current `~24.42.0` pin is a workaround for the `puppeteer-core@24.43.x` peer-publish lag.
- **Scorecard score audit.** First weekly run completed clean post-P9. When Scorecard surfaces lower-scoring checks, decide whether to SHA-pin all actions (Dependabot can still track via `# vX.Y.Z` trailing comments) or accept the score for a portfolio repo.
- **PR-gate smoke?** `pages.yml` smoke only fires on push-to-main, not on PR. A path-filtered `smoke.yml` running puppeteer on PRs touching `site/**` would catch dashboard regressions pre-merge. ~2-3 min cost per `site/` PR. Open question for next agent.
- **Tighten Dependabot auto-merge for workflow-bumps?** Workflow file changes can subtly change CI semantics; current auto-merge blesses any patch/minor including `.github/workflows/**` bumps. Consider an exclusion filter in `dependabot-automerge.yml`.

### Pipeline coverage regressions (P10) — CLOSED by descope

Pre-pivot, P10 was scoped to investigate zero-row Lever / Ashby / Personio / CSO / Eurostat returns. **All five adapters shelved by ADR-017.** Their code stays in tree, `enabled: false`. Pandas FutureWarning at `src/jobpipe/runner.py:116` already fixed in commit `48bf28e` (2026-05-15). When/if these adapters reactivate (per ADR-017 reactivation criteria), zero-row investigation reopens as part of that reactivation ADR.

### OECD SDMX unblock — CLOSED by descope

Benchmark adapters (including OECD) shelved per [ADR-017](../DECISIONS.md#adr-017--scope-cut-to-adzuna-only-post-v1-stabilisation). Unblock paths preserved as historical context: (1) OECD-issued API key, (2) CSV mirror, (3) fixed-egress proxy. When reactivated, [ADR-011](../DECISIONS.md#adr-011--oecd-sdmx-adapter-ships-disabled-cloudflare-bot-protection) remains authoritative on the Cloudflare situation.

### P6 dashboard decisions — most CLOSED by descope; one open

- ~~**Adzuna posting recency.**~~ Resolved by `max_days_old: 180` + `since_days: 180` carry-over post-pivot, plus accumulation window also at 180 days.
- **`salary_min_eur == 0` rows.** Still open — Adzuna emits a small non-zero count of zero-floored salaries. P13 dashboard work decides: surface or hide.
- ~~**CSO 4-digit ISCO coarseness.**~~ Moot — CSO shelved (ADR-017).
- ~~**Cross-source dedupe efficacy on the live mix.**~~ Moot — only Adzuna sources postings.
- ~~**Cross-day delta surfacing.**~~ Resolved by ADR-020 accumulation: `first_seen_at` / `last_seen_at` derived at publish step.

### ISCO live-match-rate measurement (post-first-Actions-run)

Run 2 of `refresh.yml` (2026-05-15, n=504, cutoff=88) measured a **55.75% fuzzy match rate** (281 fuzzy / 223 none) — below the 60% ADR-013 threshold by ~4 percentage points.

Action taken this session: lowered `DEFAULT_SCORE_CUTOFF` in `src/jobpipe/isco/tagger.py` from 88 → 85 to capture more borderline fuzzy hits. ADR-006 was not amended (the constant is in the code, not the ADR text); the deviation is recorded here and revisited after Run 3+.

A local re-run on the previous raw bundle (n=493 after recency filter) yielded fuzzy=269 / none=224 (54.56%) — the rate moved only marginally. The cutoff lowering may not be enough on its own; Run 3 (fresh data with recency floor at the source) is the next data point.

If Run 3+ stays below 60%, the LLM-fallback re-scope discussion (currently descoped via ADR-013) becomes load-bearing.

### Recency-filter coverage on non-Adzuna sources

`normalise.run()` now applies a canonical `since_days=180` floor pre-dedupe (per preset `normalise.since_days`), and the Adzuna adapter passes `max_days_old=180` as a bandwidth optimisation. ATS sources (Greenhouse/Lever/Ashby/Personio) self-prune via company removal, so the floor is rarely binding for them — but the filter still applies uniformly. Verify on Run 3 that no ATS source ever serves a posting older than 180 days; if so, the assumption holds. Otherwise consider an adapter-level optimisation (none of these expose an "updatedSince" param on the free tier today).
