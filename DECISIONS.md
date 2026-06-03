# Architecture Decisions

ADR-lite. One entry per locked architectural decision. Format:

> **Status** · **Context** · **Decision** · **Consequences**

When a decision changes, mark the old entry `Superseded` and add a new entry; don't rewrite history.

---

## ADR-001 · Orchestration: GitHub Actions cron (not Dagster)

**Status:** Accepted, 2026-05-11.

**Context:** The project targets GitHub Pages — a static-only host. Refresh cadence is daily/weekly batch. An earlier `Project_Objectives.md` spec prescribed Dagster.

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

**Status:** Accepted, 2026-05-11. **Amended by ADR-017 (2026-05-17)** — active source set narrowed to Adzuna only for v1.

**Context:** Original spec leaned on JobSpy (Indeed, LinkedIn, Glassdoor, etc.) for breadth. We run on GitHub Actions datacenter IPs.

**Decision:** Exclude JobSpy and other browser-emulation scrapers. Use API-first sources only: Adzuna (Eurozone), Greenhouse / Lever / Ashby / Personio (public board APIs), Remotive (EU filter), Hacker News Algolia.

**Consequences:**
- Indeed and LinkedIn block GH Actions datacenter IPs — JobSpy would silently fail or return empty.
- Smaller raw posting count, but reliable and ToS-clean.
- Adzuna doesn't cover Ireland directly — gap filled by ATS adapters and Remotive.
- Source adapters are uniform and lightweight (HTTP + JSON), keeping ~1,200 LoC target realistic.

---

## ADR-004 · Storage + delivery: Parquet via GitHub Releases as CDN

**Status:** Accepted, 2026-05-11. **Amended by ADR-019 (2026-05-17)** — single `latest` tag replaced by per-preset `latest-{preset_id}`; dated tag becomes `data-{preset_id}-YYYY-MM-DD`. **Amended by ADR-020 (2026-05-17)** — `latest-{preset_id}.parquet` is now a pure function over the dated archive, not a per-run snapshot.

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

**Status:** Accepted, 2026-05-11. **Amended by ADR-017 (2026-05-17)** — pattern survives; only Adzuna has `enabled: true` in v1. ATS + benchmark adapter code remains in tree, shelved via preset config.

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

## ADR-013 · HN Algolia + LLM client descoped from v1

**Status:** Accepted, 2026-05-14.

**Context:** P3 deferred Hacker News Algolia ("Who is hiring?" comment-scraping) to P4, and P4 deferred both it and the real OpenAI-compatible LLM client to a follow-up PR. v1's architectural narrative is the pluggable-adapter pattern, the deterministic ISCO path, and the free-tier deploy story — none of which require an LLM. Carrying HN + LLM into v1 adds an API-key dependency, taxonomy drift, reproducibility cost (LLM outputs vary), and a second class of CI secrets to manage. Pre-P5 cleanup pulled the trigger.

**Decision:** Both are out of scope for v1.

- Remove the `hn_algolia` block from `config/runs/data_analyst_ireland.yaml`; replace with a one-line comment referencing this ADR so the absence is intentional.
- Remove `LLM_*` env vars from `.env.example`.
- Keep `src/jobpipe/llm.py` as a documented stub: `classify_title_to_isco` + `LLMUnavailableError` are the locked contract. Nothing in the v1 pipeline imports the public function.

**Consequences:**
- Zero LLM-related env vars are required for v1 to materialise the dashboard.
- CI stays `LLM_ENABLED=false` permanently for v1; no fake LLM endpoint needed in tests.
- Re-introducing the feature post-v1 is a new ADR + one source adapter (`hn_algolia.py`) + the real client implementation in `llm.py`. The pluggable-adapter pattern (ADR-008) means no other code needs to change.
- ADR-007 (LLM optional, openai-compatible) is **not superseded** — it still describes the eventual shape. ADR-013 narrows what ships in v1.
- The dashboard story is unaffected: deterministic rapidfuzz ISCO matches are the only path users see; rows the tagger can't classify show "Unclassified" rather than waiting on an LLM fallback.

---

## ADR-014 · Local-only files excluded from the public repo

**Status:** Accepted, 2026-05-14.

**Context:** Several artefacts live in the working tree to support AI-assisted development:

- `CLAUDE.md` — verbose project guide written for Claude Code sessions (priority order of docs, hard rules, open-questions list, AI-specific git workflow).
- `.claude/` — per-IDE Claude settings, plan files, transcripts.
- `docs/sessions/` — per-session handover logs written by an AI agent at the end of each working session.
- `docs/history/` — superseded specs from earlier project phases (e.g. the original Dagster-centric `Project_Objectives.md`).

Their value is local. Pushed to a public OSS portfolio repo they (a) add maintenance overhead (every architectural change needs synchronising in two places), (b) signal AI-tool-specific scaffolding that's not part of the project's contract with contributors, and (c) can carry session state or stale prescriptions that aren't meant to inform a new reader of the project.

**Decision:** All four are gitignored and untracked.

- `.gitignore` lists `CLAUDE.md`, `.claude/`, `docs/sessions/`, and `docs/history/`.
- The load-bearing content migrates to public docs before the files are untracked: hard rules + testing discipline + git workflow → `CONTRIBUTING.md`; module layout → `docs/architecture.md`; open-questions list → `docs/open-questions.md`. The phase-by-phase narrative lives in `CHANGELOG.md`; ADRs in `DECISIONS.md` carry the *why* for every locked decision.
- Forks pick up their own AI scaffolding rather than inheriting ours.

**Consequences:**
- `git rm --cached` removes the tracked copies; the files stay on disk for local use.
- The branch has not been pushed to a public remote yet (verified at the time of this ADR), so no history rewrite is needed. If a public push had already happened, scrub-from-history (`git filter-repo --invert-paths --path <file>`) would be the required follow-up.
- New contributors get a fully self-documenting repo without needing to know about Claude Code or to wade through phase-by-phase session diaries.
- Session logs continue to be written locally — they remain useful as an AI-collaboration journal — they just don't ship.

---

## ADR-015 · httpx credential redaction filter on the CLI logger

**Status:** Accepted, 2026-05-14.

**Context:** Free-tier sources commonly pass credentials as URL query parameters. Adzuna does (`app_id` + `app_key`); future sources are likely to follow the same pattern. httpx logs full request URLs at INFO. When `jobpipe fetch --verbose` runs in a GitHub Actions workflow, the workflow log captures those URLs. Anyone with read access to the repo's Actions runs would then see the keys in plaintext.

**Decision:** Install a `CredentialScrubFilter` (in `src/jobpipe/cli.py`) on the `httpx` and `httpcore` loggers at CLI entry. The filter rewrites known credential query-param values in `LogRecord.msg` and `LogRecord.args` to `REDACTED` before the record reaches any handler. Param names are matched case-insensitively from a small list (`app_id`, `app_key`, `api_key`, `api-key`) covering current and likely-future adapters.

**Consequences:**
- The fix is central and adapter-agnostic — a new source that passes secrets via query params is automatically covered as long as its param name is on the list (or added to it). No per-adapter discipline required.
- Filter installation is idempotent and is also done before any HTTP traffic flies, so even early-init log lines are scrubbed.
- The filter does **not** redact secrets in `Authorization` / `X-Api-Key` *headers* — httpx does not log headers at INFO, so those don't currently leak. If a future source needs header-based auth and a different log level, extend the filter to inspect formatted args containing header names.
- This is a defence layer, not a substitute for not logging URLs at all. The CLI keeps `--verbose` opt-in (default is WARNING); CI workflows in P5 will run without `--verbose` by default.
- Unit-tested centrally in `tests/test_log_redaction.py`. The pattern is the same one already used by the pytest-recording VCR scrubber in `tests/conftest.py` (the project abandoned VCR after P3 but the scrub list is consistent).

---

## ADR-016 · GitHub Pages deploy via `actions/deploy-pages` from the monorepo

**Status:** Accepted, 2026-05-14.

**Context:** The architecture diagram (`docs/architecture.md`) and the README badges have referenced GitHub Pages since P0, but no decision recorded *how* the static site reaches Pages. Three options were live:

1. `actions/deploy-pages` from the same repo — modern, OIDC-friendly, Pages source = "GitHub Actions".
2. Push the built site to a `gh-pages` branch — older pattern, still works.
3. Separate repo for the dashboard, fed from this repo's Releases — cleaner separation, doubles CI overhead.

**Decision:** Option 1, monorepo.

- `site/` lives in this repo. A new `.github/workflows/pages.yml` (lands in P7) builds the Observable Framework project, uploads the build directory via `actions/upload-pages-artifact`, and deploys via `actions/deploy-pages`.
- Triggers: `workflow_run` after `refresh.yml` (P5) completes successfully, plus `workflow_dispatch` for manual deploys and `push` to `main` under `site/**` for dashboard iteration.
- Workflow permissions: `pages: write`, `id-token: write`, `contents: read`.
- Repository setting: Settings → Pages → Source = **GitHub Actions** (not "Deploy from a branch"). Documented in `docs/github-setup.md`.

**Consequences:**
- Single CI ordering: `refresh.yml` produces data, `pages.yml` rebuilds the site against the latest release. No cross-repo trigger plumbing.
- Public URL: `https://<owner>.github.io/jobmarket_analyzer/`. The Observable build needs to set its base path accordingly (Observable Framework's `root` config setting); handled in P6 when `site/` is scaffolded.
- If we ever want a custom domain or more aggressive Pages caching, the OIDC deploy path is the easier baseline to extend. Switching to a `gh-pages` branch in future would supersede this ADR.
- Data flow: `refresh.yml` uploads partitioned Parquet to GitHub Releases (per ADR-004); the Observable data loader fetches the `latest` release at build time. The dashboard does **not** read from raw repo paths, which means the Pages deploy never has to wait for a Parquet commit, and the repo doesn't bloat with binary data.
- Manual setup beyond `.github/workflows/pages.yml`: enable Pages with "GitHub Actions" source; configure Adzuna secrets; enable secret scanning + push protection. All catalogued in `docs/github-setup.md`.

---

## ADR-017 · Scope cut to Adzuna-only post-v1 stabilisation

**Status:** Accepted, 2026-05-17.

**Context:** v1 shipped with 5 source adapters (Adzuna + Greenhouse / Lever / Ashby / Personio) and 3 benchmark adapters (CSO / OECD / Eurostat). Post-P9 reality: ATS adapters returned zero rows in production runs (P10 outstanding investigation), OECD shipped disabled (ADR-011), CSO is bucket-coarse for ISCO (ADR-012), and accumulated trend analysis was not yet wired. The multi-adapter fan-out widened coverage but starved iteration: each adapter is a fragile upstream coupling, the schema must absorb every adapter's quirks, and the dashboard cannot honestly present cross-source aggregates while some sources silently zero out.

A 2026-05-17 scope conversation grounded the trade: Adzuna alone covers 19 countries (no `ie`) at 250 free-tier calls/day, ~105 calls/day at 7 EU countries × 3 keywords × 5 pages — 42 % of quota. That headroom is enough to support per-country accumulation across a multi-month window, which produces a tighter, more honest portfolio story than wide-and-shallow multi-source.

**Decision:** v1 ships with **Adzuna as the only `enabled: true` source**. ATS adapters (greenhouse / lever / ashby / personio), benchmark adapters (cso / oecd / eurostat), HN Algolia, and the LLM stub all remain in the codebase, shelved by preset configuration. No adapter code is deleted. The old single-source preset `config/runs/data_analyst_ireland.yaml` is archived to `config/runs/_archived/`; the new multi-country preset is `config/runs/data_analyst_eu.yaml`.

**Consequences:**
- Loss accepted: no Ireland-resident postings (Adzuna's `ie` is unserved). Dashboard becomes a GB-anchored EU view.
- Schema unchanged. Benchmark joins become inert until reactivation.
- The pluggable-adapter pattern (ADR-008) survives — `enabled: false` is the shelf mechanism.
- Amends ADR-003 (active source set) and ADR-008 (only Adzuna enabled in v1).
- Reactivation criteria for multi-source: **multi-country unified merge across the Adzuna-only shape must first prove stable end-to-end** (one full accumulation cycle, dashboard preset switcher live, gate at `fail_on_issues: true` without flapping). Then ATS / benchmark adapters return via a new ADR that supersedes this one.
- P10's zero-row ATS investigation is **closed by descope**, preserved in `docs/open-questions.md` as historical context.

**Amended 2026-05-18 (first-run validation):** P13 backend shipped on branch `scope/adzuna-only-multi-preset` and first matrix run (gh run 26004866509, 51 s) completed green with `gate.fail_on_issues: true` strict mode. The first preset (`data_analyst_eu`) ships with `[gb, es]` as a deliberate smoke-test scope rather than the originally-planned 7-country list — adding the remaining 5 countries is a one-line YAML edit once the dashboard side absorbs the data shape. Adzuna's "no `ie`" caveat held: GB stands in as labour-market proxy.

---

## ADR-018 · Weekly cadence + multi-country single-run

**Status:** Accepted, 2026-05-17.

**Context:** ADR-017 reduced the pipeline to a single source. The next axis is cadence × country fan-out. Two viable shapes were considered: (A) daily rotation — one country per day of week, deep paging per country; (B) all countries every run, shallower paging. A third option — daily all-countries — was ruled out by the trend-resolution analysis (see `docs/data-history-design.md` and the 2026-05-17 session log).

Option B (all countries per run, weekly cadence) gives uniform per-country sampling, simpler cron-skip recovery (next week, not next rotation cycle), and aligns with the portfolio-analytics value: weekly trend granularity is sufficient and the dataset is cheap enough that 7-day refresh costs nothing extra.

**Decision:** Weekly Monday 06:00 UTC cron (`0 6 * * 1`) plus `workflow_dispatch` for on-demand runs. The single-preset multi-country fan-out happens inside one workflow run: `sources.adzuna.countries: [gb, de, fr, nl, es, it, pl]` — the existing `for country in cfg.countries` loop in `src/jobpipe/sources/adzuna.py:85-91` handles it without code change.

**Consequences:**
- Per-run cost ≈ 7 countries × 3 keywords × 5 pages = **105 calls** (42 % of Adzuna's 250/day free-tier quota).
- 52 cron firings/year vs 365 — cron-drift / skip blast radius is one week (down from one day, but acceptable for trend analytics).
- Closure detection lag = 7 days (a posting that disappears from upstream takes one cron to register as `last_seen_at < generated_at`).
- `min_interval_hours` preset knob deprecated for Adzuna (cron schedule is now authoritative).
- Future-proofing: if a per-country call cost rises sharply (Adzuna adds aggressive paging caps, or we widen `keywords`), drop to two-day rotation (~3.5 countries/run) — preserves the all-in-one-run simplicity.

---

## ADR-019 · Multi-preset `latest-{preset_id}` release naming

**Status:** Accepted, 2026-05-17.

**Context:** A single `latest` release tag (per ADR-004) couples the pipeline to one preset at a time. The project now anticipates multiple parallel presets (`data_analyst_eu`, future `software_developer_eu`, etc.) running on independent crons or shared matrix runs. Without preset-scoped naming, two parallel runs would race on the same `latest` tag, the same `data-YYYY-MM-DD` tag, and the same asset filenames — `gh release upload --clobber` matches by name and would lose one preset's data.

**Decision:** Release tags and asset filenames are scoped by `preset_id`:

- Moving tag: `latest-{preset_id}` (e.g. `latest-data_analyst_eu`)
- Dated tag: `data-{preset_id}-YYYY-MM-DD`
- Asset filename: `latest-{preset_id}.parquet` (single flat parquet, partition_by unchanged)
- Workflow concurrency group: `refresh-${{ matrix.preset }}` (allows cross-preset parallelism, serialises same-preset)
- GitHub Actions strategy: `strategy.matrix.preset: [...]` in `refresh.yml`, hardcoded preset references replaced with `config/runs/${{ matrix.preset }}.yaml`

**Consequences:**
- Multiple presets run in parallel without artifact collision.
- Dashboard data loader must enumerate `latest-*` release tags (and/or read a presets manifest) instead of hardcoding `latest`. See ADR-020 for the dashboard switcher pattern.
- `gh release list` paging applies — at any plausible preset count (< 30) this is fine; revisit if presets explode.
- `manifest.json` already carries `preset_id` (see `src/jobpipe/duckdb_io.py`) — gate command lookup unbroken.
- Amends ADR-004 (single `latest` assumption). ADR-004's storage cost and "free CDN" rationale unchanged.

**Amended 2026-05-18 (first-run validation):** Naming shipped as designed. First release pair created cleanly: `latest-data_analyst_eu` (moving) + `data-data_analyst_eu-2026-05-17` (immutable). Wipe-then-upload on the moving tag preserved per [[pitfall-release-clobber-zombies]]; the renamed asset (`latest-data_analyst_eu.parquet` replacing the legacy `postings__postings.parquet`) did not leave zombies because the new tag started empty.

---

## ADR-020 · Accumulated dataset via pure-function recompute

**Status:** Accepted, 2026-05-17. Promotes `docs/data-history-design.md` (P9 design) from design-only to accepted.

**Context:** v1 pre-pivot semantics: each run is a snapshot, `latest` is overwritten with that run's data, prior dated releases accumulate as a side effect that no consumer reads. This forecloses trend analysis: `posted_at` (upstream-stable) plus `ingested_at` (advances per run) carry all the information needed for `first_seen_at` / `last_seen_at` derivation, but only if multiple runs are unioned.

Two unification models were considered: (B) stateful append-merge — each run downloads prior `latest`, appends today's data, dedupes, republishes; (D) pure-function recompute — each run unions the last N dated releases from the immutable archive, GROUP BY `posting_id`, MIN/MAX `ingested_at` → emits a freshly computed `latest`. (B) is fragile under corruption (errors propagate forward); (D) is recoverable from archive at any point.

**Decision:** `latest-{preset_id}.parquet` is computed every run as a **pure function** of `(archive_window, window_days)`:

```sql
WITH archive AS (
  SELECT * FROM read_parquet('data-{preset_id}-*/postings.parquet')
  WHERE ingested_at >= now() - INTERVAL window_days DAYS
)
SELECT
  posting_id,
  MIN(ingested_at) AS first_seen_at,
  MAX(ingested_at) AS last_seen_at,
  ANY_VALUE(title), ANY_VALUE(company), ...
FROM archive
GROUP BY posting_id;
```

Implementation: `src/jobpipe/duckdb_io.py:export_accumulated(dated_paths, out, preset_id)`. Wired through `runner.run_publish()` via preset YAML `publish.accumulate_window_days` (default: 180 days, matches existing `normalise.since_days` floor). Adds two nullable columns to `PostingSchema`: `first_seen_at: datetime`, `last_seen_at: datetime` (populated only by accumulated artifact, not per-source adapters).

**Consequences:**
- `latest-{preset_id}.parquet` is **always recomputable** from the dated archive. Bug in publish step → re-run, get correct result. No state drift.
- Window is a config value, not a destructive operation. Change `accumulate_window_days: 90` → `365` → next publish rebuilds. No data migration.
- Archive retention: **forever** (no `cleanup.yml`). GH Releases on public repos have no published storage cap; ~1.3 GB/yr per preset is acceptable. Revisit only if it becomes a measured problem.
- Closure detection: `last_seen_at < generated_at - one_cron_interval` signals upstream closure.
- Dashboard `latest` artifact grows from ~23 KB (single snapshot) to ~150-250 MB (180-day accumulation). This **forces P8 forward** — DuckDB-WASM cold-loading 200 MB is unacceptable. P8's planned fix (build-time data loaders + pre-aggregated per-chart parquets) must ship in lockstep with accumulation, or before. P8 is folded into the next implementation phase per `docs/open-questions.md`.
- Backfill: first run after pivot derives `first_seen_at` from any existing dated releases within the window (legacy `data-YYYY-MM-DD` plus new `data-{preset_id}-YYYY-MM-DD`). Pre-pivot releases lack the new fields → safe to ignore for any field they don't carry; safe to include for `posting_id` / `ingested_at` derivation.

**Amended 2026-05-18 (first-run validation):** Implementation shipped with two non-obvious adjustments not captured in the original design:

1. **Tz-aware NaT injection is mandatory.** Per-source frames must inject `first_seen_at` / `last_seen_at` as `pd.Series(pd.NaT, dtype="datetime64[ns, UTC]")` — a bare `pd.NaT` writes to parquet as `TIMESTAMP_NS` (no tz) while `ingested_at` writes as `TIMESTAMP WITH TIME ZONE`. DuckDB's `COALESCE` inside the MIN/MAX aggregation refuses mixed-tz inputs without an explicit cast, so the accumulation SQL also wraps the inputs in `CAST(... AS TIMESTAMP WITH TIME ZONE)`. Helper `jobpipe.schemas.inject_accumulation_cols(df)` does the injection at every validate site (fetch_sources, normalise.run, adapter smoke tests).
2. **Greenfield-Option-A confirmed.** First run for a new preset finds no `data-{preset_id}-*` archive entries. `_accumulate_into_latest` logs "first-run, no archive — using fresh fetch only" and ships the per-source frame unmodified (all `first_seen_at` / `last_seen_at` columns NaT). Week-2 onward: `MIN(COALESCE(first_seen_at, ingested_at))` correctly derives the historical floor from the legacy snapshot's `ingested_at`. No backfill of pre-pivot single-source releases attempted — preset-provenance stays clean.

Recorded as pitfalls: [[pitfall-pandas-naT-not-tz-aware-parquet]] (new), [[pitfall-duckdb-coalesce-mixed-tz]] (new).

---

## ADR-022 · PostingSchema v2 — persist 5 Adzuna fields + skills

**Status:** Accepted, 2026-05-18.

**Context:** The Adzuna `/jobs/{country}/search/{page}` response returns several fields the adapter drops at `_normalise_row` — they survive only inside `raw_payload` JSON: `category.label` (27-bucket Adzuna taxonomy), `contract_type` (permanent/contract), `contract_time` (full_time/part_time), `description` (500-char-truncated free text), `location.area[]` (5-level hierarchy). Dashboard panels users will ask for first (Adzuna-category × ISCO matcher cross-tab, permanent-vs-contract salary delta, location drill-down without geocoding) are invisible without these. Full empirical field inventory captured at [`docs/references/adzuna_api.md`](docs/references/adzuna_api.md). Separately, the dataset had no skill signal — ADR-023 adds the `skills` column on top of the same schema bump.

**Decision:** Bump `MANIFEST_SCHEMA_VERSION` from `"1"` → `"2"` and add six nullable columns to `PostingSchema`:

| Column | Dtype | Constraint | Source |
|---|---|---|---|
| `adzuna_category` | str | `nullable` | Adzuna `category.label` |
| `contract_type` | str | `nullable` (no enum — see amendment) | Adzuna `contract_type` (~36% populated) |
| `contract_time` | str | `nullable` (no enum — see amendment) | Adzuna `contract_time` (~42% populated) |
| `description` | str | `str_length max=1000` | Adzuna `description` (500 chars + ellipsis; cap raised for upstream drift) |
| `location_area` | list[str] | class-level `@pa.check` accepts list / numpy.ndarray / null | Adzuna `location.area[]` |
| `skills` | list[str] | same check shape | Populated by ADR-023's ESCO tagger; `[]` when no matches |

`category.tag` (slug) is **not** persisted — `category.label` is the human-readable form, and the slug remains recoverable from `raw_payload`.

**Amendment 2026-05-18** (pre-merge review): `contract_type` / `contract_time` `isin` constraints DROPPED. Adzuna's own API reference notes "other values likely exist" (e.g. `temporary`, `apprenticeship`). A new value on a single posting would fail strict-mode pandera validation and red-gate the entire weekly run — unacceptable on an unattended cron. `description` cap raised 600 → 1000 for the same reason (the 100-char buffer over Adzuna's observational 500-char truncation was thin). Value-set surveillance moves to the gate step in a follow-up.

Implementation pattern matches ADR-020 / commit `24192ca` (first/last_seen_at addition):

1. Adapter (`src/jobpipe/sources/adzuna.py`) emits the columns in `_normalise_row`.
2. `PostingSchema` declares them with `nullable=True` so non-Adzuna adapters (Greenhouse / Lever / Ashby / Personio, currently `enabled: false`) don't break.
3. `schemas.inject_accumulation_cols` extended with a sibling tuple `_SOURCE_OPTIONAL_OBJECT_COLS` — fills missing-column cases with all-null object Series so the strict PostingSchema accepts non-Adzuna frames.
4. **`_ACCUMULATE_ANY_VALUE_COLS` in `duckdb_io.py:171` extended** — without this the new columns get silently dropped by `export_accumulated()`'s explicit SELECT projection.
5. New drift-guard test `tests/test_schema_accumulate_drift_guard.py` fails the build if any future PostingSchema column is missing from that tuple (modulo the explicit `_EXCLUDED` set).

**Consequences:**
- `union_by_name=true` in `export_accumulated` makes the schema bump automatically forward-compatible: historical dated releases lack the columns, the UNION NULL-fills, no re-encoding of the archive is needed.
- Object-dtype list columns survive pyarrow round-trip as `numpy.ndarray`, not `list` — the `pa.Check` lambda must accept both shapes. Recorded as pitfall [[pitfall-pyarrow-list-roundtrip-as-ndarray]].
- DuckDB `ANY_VALUE` over a LIST column works without modification (probed 2026-05-18); no `arg_max` fallback needed.
- `description` adds ~500 KB per 1000 rows to the published parquet; at 180-day accumulation this is a few MB, well inside budget.
- 308 → 321 tests after PR; live end-to-end run validated against 982 fresh Adzuna rows.

Recorded as pitfalls: [[pitfall-pyarrow-list-roundtrip-as-ndarray]] (new).

---

## ADR-023 · Skill enrichment via ESCO Pillar B + Aho-Corasick, scoped by preset `isco_focus`

**Status:** Accepted, 2026-05-18.

**Context:** The user-facing dashboard needs a skills view ("what tools / languages do data-analyst postings ask for") but Adzuna's `description` is hard-truncated at 500 chars and we already have ESCO's occupation taxonomy live in the ISCO matcher — adding ESCO's sister Pillar B (skills/competences/knowledge) is the path of least resistance. Three design questions had multiple defensible answers; user picked all four locks (see plan `generic-honking-hennessy`):

1. **Dictionary source:** ESCO Pillar B (~13.9k skills), not a curated YAML list.
2. **Output shape:** single `skills: list[str]` column.
3. **Extractor:** word-boundary regex / multi-keyword scan; no LLM.
4. **Pipeline slot:** embedded inside `normalise.run()` after the ISCO tagger — mirrors the existing enrichment precedent, no new CLI subcommand, no new workflow step.

ESCO's public REST API caps listing endpoints at offset=100 (recorded as [[pitfall-esco-api]] from the ISCO work) so the snapshot can't be built by walking the skills concept-scheme directly. The official ESCO CSV bundle download is email-gated — not viable for unattended CI. The **tabiya-tech open-dataset** (<https://github.com/tabiya-tech/tabiya-open-dataset>) is the only stable, free public mirror; ships ESCO v1.1.1 as CSVs reachable via `raw.githubusercontent.com`. v1.2.1 (current upstream) is a future bump when tabiya releases it.

**Decision:** Build a committed `config/esco/skills_labels.parquet` snapshot from the tabiya mirror; match against `title + " " + description` with an Aho-Corasick automaton; filter the skill dictionary to the preset's `isco_focus` codes BEFORE building the automaton.

Snapshot schema (committed at ~2.2 MB, 13,896 rows):

| col | dtype | source |
|---|---|---|
| `skill_uri` | str | ESCO canonical URI |
| `preferred_label` | str | `PREFERREDLABEL` from `skills.csv` |
| `alt_labels` | list[str] | `ALTLABELS` (newline-split) |
| `skill_type` | str | `skill/competence` (10 831) or `knowledge` (3 059) |
| `reuse_level` | str | `sector-specific` / `cross-sector` / `occupation-specific` / `transversal` |
| `related_isco_codes` | list[str] | union of ISCO-08 codes whose occupations link this skill via `essential` or `optional` relation, joined through `occupation_skill_relations.csv` × `occupations.csv` |

Tagger architecture (`src/jobpipe/skills/tagger.py`):

- One `ahocorasick.Automaton` per call. Keys are lowercased preferred + alt labels; payload is the preferred label only (deduplicated output).
- Word-boundary post-filter: Aho-Corasick is substring-based, so a match at `[start..end]` is accepted only if `haystack[start-1]` and `haystack[end]` are non-word chars. Stops "Java" matching "Javascript", "SQL" matching "PostgreSQL".
- Empty matches → `[]` (not `None`) for parquet list-column compatibility.
- **`focus_isco` parameter** (passed from `preset.isco_focus`): filters the 13.9k dictionary to skills whose `related_isco_codes` intersects the focus set. Empirically reduces noise from 13,896 → 931 skills on the `data_analyst_eu` preset, killing false positives like "packaging engineering", "journalism", "instrumentation equipment" that share generic English words with data-analyst JDs.

Preset `data_analyst_eu.yaml` expanded `isco_focus` from `["2521", "2511"]` (Database admins + Systems analysts) to the seven-code data-analytics family: **`2511`** Systems analysts, **`2519`** Software/apps developers and analysts NEC, **`2521`** Database admins, **`2529`** Database/network NEC, **`2421`** Management & organization analysts, **`2120`** Mathematicians/actuaries/statisticians, **`1330`** ICT service managers. The codes were picked empirically by querying which ISCO codes the canonical data-analyst skills (SQL, Python, BI, ML, data analytics, etc.) link to in the snapshot.

`pyahocorasick==2.3.1` added to `pyproject.toml`. Pure regex alternation over 13k patterns backtracks catastrophically; flashtext is unmaintained; pyahocorasick is the right shape and ships Windows + Linux wheels.

**Consequences:**
- Empirical match rate on 982 live rows: **89.0 % postings tagged** with mean 1.26 skills/posting. Top hits: statistics (823), SQL (59), business intelligence (53), data analytics (46), machine learning (27), Microsoft Access (23), data models (19), ETL tools (12), Python (10).
- Switching presets (e.g. `software_developer_eu`) requires changing `isco_focus` in the preset YAML — no re-snapshot, no code change. The committed snapshot is the full Pillar B; runtime scoping decides what's relevant.
- Re-run the snapshot script (`scripts/build_esco_skills_snapshot.py`) only when tabiya publishes a new ESCO version. Caches CSVs under `.cache/esco/` (gitignored).
- English-only for v1 — multilingual ESCO labels exist but our markets so far (gb + es) post mostly in English (confirmed by [[project-p13-first-run-2026-05-17]]). Re-open if widening to FR / DE / IT / PL surfaces meaningful skill-recall drop.
- `tabiya-tech/tabiya-open-dataset` is the supply-chain dependency for the snapshot — recorded as reference [[reference-esco-tabiya-mirror]].
- LLM extraction stays out of scope. `src/jobpipe/llm.py` remains the unused scaffold for a future hybrid mode.
- No new CLI subcommand. No new workflow step. The refresh.yml steps are unchanged — the tagger runs inside the existing `normalise` step.

Recorded as pitfalls: [[pitfall-aho-corasick-word-boundary-needed]] (new). Reference: [[reference-esco-tabiya-mirror]] (new).

---

## ADR-021 · No per-country keyword translation table in v1

**Status:** Accepted, 2026-05-18.

**Context:** Going into the first multi-country run, the open hypothesis was: "non-English Adzuna markets (ES, DE, FR, IT, NL, PL) will return locally-titled postings (e.g. `Analista de datos`) that fuzzy-match poorly against the English-only ESCO label set, requiring a per-country keyword translation map (`keywords_by_country: {de: [Datenanalyst, ...], es: [analista de datos, ...]}`) and a multilingual ESCO snapshot before widening the country scope."

**Decision:** No translation table for v1. The first run (2026-05-17, gh run 26004866509, gb+es smoke scope, 992 rows) measured **ES at 70.6 % ISCO match rate vs GB at 53.5 %** — ES match rate is *higher*, not lower. Sampling 15 random ES titles surfaced only one with Spanish content ("Prácticas de Data Analyst", and even that is half-English). Adzuna's Spanish corpus, when queried with `what=data analyst`, returns mostly English-titled tech postings — the Spanish tech-sector job market labels these roles in English. The actual lever for raising the GB rate is **ISCO label coverage** ("Analytics Engineer", "Power BI Developer", "BI Developer" don't appear in the current ESCO snapshot — adding them lifts GB ~10 pp).

**Consequences:**
- Adzuna preset stays single-keyword-list across all countries. `sources.adzuna.keywords: ["data analyst", "analytics engineer", "bi analyst"]` is the v1 shape.
- Re-open this decision under any of: (a) widening to DE / FR / IT / PL surfaces materially lower match rates than ES (suggests Spanish tech market is the exception, not the norm); (b) the role family expands beyond data-analyst-flavoured roles, where market-localisation is more common (e.g. construction, healthcare, retail); (c) Adzuna's matching behaviour changes upstream.
- Cheap pre-v1.1 win: extend `config/esco/isco08_labels.parquet` with the three missing English titles. Single PR, no schema work, no translation infrastructure.

---

## ADR-024 · Filter state persistence via URL search params

**Status:** Accepted, 2026-05-19.

**Context:** The 5-page dashboard restructure (ADR-019 era) introduced per-page sticky filter cards (country / ISCO major / salary range / posted-after / preset). Observable Framework's default routing is full HTTP page reloads on sidebar navigation, so cell-scoped `view()` re-initializes every filter on each page. User report: setting a country filter on `/` and clicking "Geography" reset everything; bookmarks didn't preserve state; deep links to filtered views didn't exist.

The team also considered (and rejected) migrating from imperative `DuckDBClient.of({postings: FileAttachment(...)})` + `db.query(stringSql)` to declarative frontmatter `sql: { postings: ./data/postings.parquet }` + fenced ```sql id=name``` blocks. Both are first-class per Observable docs, but fenced blocks parameter-bind `${...}` interpolations as a SQL-injection safety feature — our `whereClause()` returns a SQL fragment string, which produces `Parser Error: syntax error at or near "?"` when parameter-bound. See `pitfall-framework-sql-fenced-block-param-binding` memory. The geography canary was reverted; chart queries stay on `DuckDBClient.of` + `db.query`.

**Decision:** Persist filter state via URL search params using vanilla DOM APIs (`URLSearchParams` + `history.replaceState`); no SPA, no localStorage as primary store. Three pieces:

1. `site/src/components/filterState.js` — `readFromURL()` returns `{country, iscoMajor, salaryLo, salaryHi, dateFrom, dateTo, preset}` for the filter constructors to seed defaults; `writeToURL(filters, defaults)` omits any param equal to its default (keeps URLs clean when filters at rest), then calls `history.replaceState` (no navigation, no history pollution).
2. Filter primitives (`countrySelect`, `iscoMajorSelect`, `salaryRange`, `dateRange`, `presetSelect`) gain an optional `default` second arg with a defensive guard: a URL value not present in current options falls back to the hardcoded default (URL might carry a stale value not in the current data snapshot).
3. `observablehq.config.js` `head:` config injects a tiny delegated click listener (capture phase) that, on click of any `#observablehq-sidebar a[href]` or `nav a[rel='next'|'prev']`, reads `window.location.search` at click time, appends it to the destination, and assigns to `window.location.href` (no `preventDefault` race; reads fresh state, not stale baked-in hrefs).

URL key naming:

| Filter | URL key | Encoding |
|---|---|---|
| Country | `country` | encodeURIComponent value; omit when `(all)` |
| ISCO major | `isco` | 1-digit code; omit when `(all)` |
| Salary min/max | `salary_lo` / `salary_hi` | integer; omit at bound default |
| Date from/to | `date_from` / `date_to` | `YYYY-MM-DD`; omit at dataset min/max |
| Preset | `preset` | raw id; omit when first preset |

Smoke (`site/scripts/smoke.mjs`) extended to walk all 5 pages in both dev and dist phases (was 1 page only). Caught the parameter-binding regression on geography during the rejected frontmatter `sql:` experiment.

**Consequences:**
- Shareable / bookmarkable filtered URLs (`/skills?country=France&isco=2&salary_lo=40000`).
- Filters survive page navigation in both directions (sidebar + footer next/prev rewrite covers all internal anchors).
- Hard refresh and back-button reproduce filter state.
- No persistence to localStorage — when the user closes the tab, filter state is gone unless bookmarked. Acceptable trade-off (shareable links > cross-session stickiness for a public dashboard).
- Cross-page navigation still triggers a full page reload (the same DuckDB-WASM cold-start cost as before; browser HTTP cache + WebAssembly compile cache make revisits cheap). Documented in methodology page.
- No SPA migration — explicitly rejected. Framework's documented routing model stays intact.
- Compatible with the eventual multi-preset switcher (ADR-019); `preset` is just another URL param.

Memory: [[pitfall-framework-sql-fenced-block-param-binding]] (new), [[feedback-duckdb-first-class-in-framework]] (refined to acknowledge both `sql:` frontmatter and `DuckDBClient.of` are first-class).

---

## ADR-025 · PostingSchema v3 — drop dead-weight cols, ternary work_arrangement, /details/ off by default

**Status:** Accepted, 2026-05-29.

**Context:** Shape audit of the local `latest-data_analyst_eu.parquet` (sample from the 2026-05-17 P13 first run) surfaced four parallel issues:

- `location_raw` was a free-text display string from Adzuna's `location.display_name`; superseded by the structured `location_area: list[str]` landed in ADR-022 (schema v2). Two adjacent columns carrying the same signal in two shapes is overhead with no payoff — the dashboard already projects neither.
- `region` was a schema slot every adapter emitted as `None`. Always-NULL columns make storage cheap but mislead future contributors who assume the slot is populated.
- `remote: bool | None` (introduced pre-pivot) conflated full-remote with hybrid, the two states most users want to distinguish.
- `year_month` was synthesized at publish time (`strftime(posted_at, '%Y-%m')`) as a partition-key column. The active preset uses `partition_by: []` (per ADR-004's flat-release variant), so `year_month` was inert data column overhead with zero consumer.

In parallel, salary midpoints like `52499.500000001` from `(min+max)/2` float-math leaked into the parquet — visually noisy without conveying real precision.

The pivot from `remote: bool` to a structured arrangement signal raised a sub-question: where does the body to scan for keywords come from? Adzuna's `/search` returns `description` truncated to ~500 chars + `…`. The full body lives only at `/v1/api/jobs/{country}/details/{id}` — one HTTP call per posting. Verified empirically (2026-05-29 run, 966 postings): full-body inference reaches **22%** classified vs **~15%** projected from truncated alone. **Marginal lift is ~7 percentage points at a cost of ~50× wall-time** on a fresh checkout (~30 min vs ~1 min). Disk cache + archive hydration drop steady-state cost ~80%, but the first-run cost is paid every time the cache is wiped.

**Decision:** Four-part v3 schema migration.

1. **Drop the four columns** above. `MANIFEST_SCHEMA_VERSION` bumps `"2"` → `"3"`. Old archives stay readable via `export_accumulated()`'s `union_by_name=true` (missing cols → NULL).
2. **Add `work_arrangement: Series[str]`** with `isin=["remote","hybrid","onsite"]`, nullable. Replaces the dropped `remote: bool` slot. `isin` constraint is safe here (unlike `contract_type` per ADR-022's wire-tolerant note) because the producer is our own deterministic tagger, not an upstream API.
3. **Round `salary_annual_eur_p50` to 2 decimals** inside `_recompute_p50()` — once at the source. Dashboard never sees the precision-rot value.
4. **Tagger ships ON, fetcher ships OFF by default.** `jobpipe.work_arrangement.tagger.tag(df, lookup=None)` runs unconditionally in `normalise.run()` against the truncated `description` column already on the frame — zero quota cost, ~15% coverage. The `/details/{id}` fetcher (`jobpipe.work_arrangement.fetcher.DetailsFetcher`) is opt-in via preset YAML `normalise.work_arrangement.enabled: true`. The active `data_analyst_eu.yaml` preset has it `false` for v1.

The tagger uses `\b`-anchored multilingual regex (en/es/de/fr/it) keyed by ISO-639 code, with a per-country language map (English always combined). Tiebreak rule: **hybrid > remote > onsite** — a "hybrid" mention overrides any "remote" hit since hybrid postings frequently advertise "remote flexibility."

The fetcher has retry (tenacity, 3 attempts), disk cache at `data/cache/work_arrangement/{posting_id}.txt`, in-memory shadow, configurable inter-call sleep (default 0.5s), 404 → silent NULL, and credential redaction on wrapped error messages (post-fix; see consequences).

**Consequences:**
- `_ACCUMULATE_ANY_VALUE_COLS` drops from 26 → 22 cols. Archive backfill not required; ADR-020 union semantics handle the v2→v3 transition transparently.
- Dashboard `site/src/data/postings.parquet.js` projection unaffected — it never referenced the dropped columns. `work_arrangement` is NOT in the current projection; surface via a follow-up PR if a chart needs it.
- Fixture cleanup: ~7 test files needed scrubbing of `location_raw` / `region` / `remote` / `year_month` row constructors. Pandera strict mode caught every miss loudly.
- Empirical coverage at v1 (tagger only, `/details/` off): ~15-18% classified, ~82% NULL. ES significantly weaker than GB (~12% vs ~28%) due to thin Spanish keyword dictionary — known gap, ES dictionary expansion is a cheap follow-up.
- The `remote: bool` → `work_arrangement: str` rename trades one bit per row for ~5 bytes per row. Worth it — `hybrid` was previously indistinguishable from `remote`.
- **Security fix in same branch:** the fetcher initially re-raised `httpx.HTTPStatusError` wrapped in `AdzunaDetailsError(f"...: {exc}")`, and the runner logs the wrapped message at WARNING. `str(httpx.HTTPStatusError)` echoes the request URL verbatim, including `?app_id=...&app_key=...` query params. The ADR-015 `CredentialScrubFilter` is only attached to `httpx` / `httpcore` loggers — the `jobpipe.runner` logger bypassed it. Mitigation: copy the same `_CREDENTIAL_RE` substitution into `fetcher.py` before re-raising. Added `test_persistent_5xx_error_message_redacts_credentials` to lock it in.
- Reactivation criteria for `/details/{id}`: dashboard demonstrates demand for higher work_arrangement coverage AND Spanish keyword dictionary already expanded (which would lift coverage cheaper than HTTP). Then re-open via a successor ADR.

Memory: [[project-schema-v3-landed-2026-05-29]], [[pitfall-fetcher-creds-leak-in-wrapped-error]], [[feedback-truncated-description-first-fetcher-opt-in]].

---
