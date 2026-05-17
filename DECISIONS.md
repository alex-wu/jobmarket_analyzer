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

---
