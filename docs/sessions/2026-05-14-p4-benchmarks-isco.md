# Session log — 2026-05-14 · P4 benchmarks + ISCO tagger

> Opened on `p4-benchmarks-isco-hn` (one `pre: snapshot` ahead of `main` after the P3 squash-merge). Closed with the **benchmarks-and-ISCO slice of P4 complete**: ESCO snapshot + rapidfuzz tagger + three benchmark adapters (CSO, OECD, Eurostat) + runner fan-out + sibling `benchmarks.parquet`. **HN Algolia and the LLM ISCO fallback are explicitly deferred** to a follow-up PR; OECD ships disabled (Cloudflare blocker, see Issues §3). 10 feature commits + 1 chore + 1 anchor on the branch, ready for squash-merge.

## Premise

User asked: "proceed with phase 4 for the benchmark data point." Plan-mode workflow ran: explored the architecture (BenchmarkSchema sibling-parquet shape, postings-side ISCO nullability, dashboard's client-side join intent), asked two scoping questions, and got:

| Question | Choice |
|---|---|
| P4 scope | Benchmarks + ISCO tagger (defer HN Algolia + LLM fallback) |
| Refresh cadence | Per-bench `min_interval_hours` throttle |

Plan saved to `~/.claude/plans/proceeed-with-phase-4-snug-manatee.md`.

## What landed

### Pre-flight (no commits)

WebFetch / httpx probes against each upstream source to confirm shape before writing parsers (P3 discipline):

| Source | Result |
|---|---|
| **CSO PxStat `EHA05`** | wrong dataset — NACE-only, no occupation axis |
| **CSO PxStat `EHQ03`** | 200 OK, JSON-stat 2.0. Has 3-bucket "Type of Employee" axis (`C02397V02888` = managers+profs / clerical / manual). **NOT** 4-digit ISCO — adapter maps via leading digit. |
| **OECD `sdmx.oecd.org/public/rest/...`** | **HTTP 403 Cloudflare bot-protection challenge.** Same wall on the dataflow listing and the data endpoint. |
| **Eurostat `earn_ses18_07`** | 404 (deprecated code) |
| **Eurostat `earn_ses_pub2s`** | 200 OK but no `isco08` dim |
| **Eurostat `earn_ses_annual`** | 200 OK, full ISCO breakdown (`OC1`, `OC25`, `OC2511`). Picked. |
| **ESCO `/api/search?type=occupation` pagination** | broken past offset=100. Same for `/api/resource/concept?isInScheme=...`. Pivoted to ISCO-tree walk via `narrowerConcept` / `narrowerOccupation`. |
| **ESCO single-concept resolve `isco/C2511`** | 200 OK, includes `narrowerOccupation` (18 ESCO occupations under "Systems analysts") |

### Commits on `p4-benchmarks-isco-hn`

| # | Hash | Subject |
|---|---|---|
| 1 | `230f787` | `pre: snapshot` (pre-P4 anchor) |
| 2 | `7bae4f1` | `chore: add ipykernel + pin pandas in dev dep group` (cleared dirty tree) |
| 3 | `57076d2` | `feat(esco): static ISCO-08 label snapshot` |
| 4 | `da2d8eb` | `feat(isco): rapidfuzz tagger + label loader` |
| 5 | `5e0c546` | `feat(normalise): wire ISCO tagger into pipeline` |
| 6 | `27bd64f` | `feat(llm): stub interface for follow-up PR` |
| 7 | `ce9bdb5` | `feat(benchmarks): shared helpers + throttle decision` |
| 8 | `ce7cd4d` | `feat(benchmarks): CSO PxStat (EHQ03) adapter` |
| 9 | `249b2d4` | `feat(benchmarks): OECD SDMX-JSON adapter` |
| 10 | `7b21f85` | `feat(benchmarks): Eurostat SES (earn_ses_annual) adapter` |
| 11 | `26488ef` | `feat(runner): benchmark fan-out + sibling parquet` |
| 12 | _this_ | `docs(p4): adding-a-benchmark.md, CHANGELOG, session log` |

### Code landed

- **`scripts/build_esco_snapshot.py`** — one-shot ESCO snapshot builder. Walks the ISCO concept tree (BFS from 10 major groups) instead of trying the broken `/api/search` pagination. ~620 HTTP calls, ~30 s.
- **`config/esco/isco08_labels.parquet`** — 2 137 labels × 436 unique 4-digit ISCO codes, 36 KB. Provenance + EUPL-1.2 attribution in `config/esco/README.md`.
- **`src/jobpipe/isco/loader.py`** (100% cov) — `load_isco_labels(path=...)` cached per resolved path, validates 4-digit codes.
- **`src/jobpipe/isco/tagger.py`** (92% cov) — `tag(df, labels_df, score_cutoff=88)`. Pure. Cleans titles (strip parentheticals, lowercase, drop non-alnum), runs `rapidfuzz.process.extractOne(scorer=token_set_ratio)`.
- **`src/jobpipe/llm.py`** (100% cov) — `LLMUnavailableError` + `classify_title_to_isco(title, allowed_codes)`. Raises immediately when `LLM_ENABLED=false`; `NotImplementedError` otherwise. Not invoked anywhere this phase — locks the contract for the follow-up.
- **`src/jobpipe/benchmarks/_common.py`** (98% cov) — `last_fetch_mtime`, `should_skip`, `convert_benchmark_to_eur`.
- **`src/jobpipe/benchmarks/cso.py`** (84% cov) — CSO `EHQ03` PxStat JSON-stat 2.0 adapter. EUR-native. Weekly earnings annualised x52. Maps 4-digit ISCO to 3-bucket "Type of Employee" via leading digit. Documented coarseness.
- **`src/jobpipe/benchmarks/oecd.py`** (89% cov) — generic SDMX-JSON 2.0 adapter, dataflow + key configurable. Handles per-observation `UNIT_MEASURE` currency. Cloudflare-aware: detects HTML interstitial via content-type and returns empty.
- **`src/jobpipe/benchmarks/eurostat.py`** (86% cov) — `earn_ses_annual` JSON-stat 2.0 adapter. Strips `OC` prefix on isco08; keeps only 4-digit leaves. Selects latest SES vintage automatically.
- **`src/jobpipe/runner.py`** — `fetch_benchmarks(preset, out_root, now=None)` + `_load_latest_benchmarks(out_root)`. Wired into `run_fetch` (after postings) and `run_normalise` (sibling parquet write).
- **`src/jobpipe/normalise.py`** — extended signature: `run(raw, rates, labels_df=None)`. ISCO tagging slotted between `_recompute_p50` and `dedupe.cross_source`. When `labels_df is None`, falls back to `isco_loader.load_isco_labels()` for the CLI path.
- **`src/jobpipe/benchmarks/__init__.py`** — `BenchmarkAdapter.fetch` Protocol signature extended with optional `rates` kwarg.
- **`src/jobpipe/schemas.py`** — `BenchmarkSchema.Config.strict = True` (was relaxed in the P0-P3 window).

### Tests
- 18 ISCO tests (loader + tagger)
- 3 LLM stub tests
- 13 shared-helpers tests
- 14 CSO tests + 12 OECD tests + 12 Eurostat tests = 38 adapter tests
- 5 new runner tests (benchmark fan-out: happy / fail-isolated / throttle-skip / no-benchmarks / sibling-parquet end-to-end)
- 2 new normalise tests (labels populated + default-snapshot smoke)
- Smoke `test_benchmark_registry_lists_known_adapters` replaces the P0 stub.

Total: 223 tests pass, **92.32% overall coverage** (gate: 80% line / 70% branch). Per-adapter benchmark coverage is in the mid-80s — below the team-norm 90% but acceptable given that ~10% of missed lines are sparse-value JSON-stat branches that aren't worth synthesising fixtures for.

### Config / docs
- `config/runs/data_analyst_ireland.yaml` — `cso` + `eurostat` flipped to `enabled: true`; per-bench `min_interval_hours` set (168/720/720). `oecd` kept `enabled: false` with a 5-line rationale citing the Cloudflare blocker.
- `docs/adding-a-benchmark.md` — appended "Throttling" + "Fail-isolation" sections; expanded the EU benchmarks paragraph with the CSO coarseness, OECD blocker, and Eurostat `OC`-prefix detail.
- `README.md` — flipped the P4 checkbox; updated the status line.
- `CHANGELOG.md` — full P4 `[Unreleased]` block.

## Issues + resolutions

| # | Encountered | Resolution |
|---|---|---|
| 1 | First-pass plan picked `CSO EHA05` — turned out to be NACE-only (sector × time × stat, no occupation axis). | Pivoted to `EHQ03` after a second probe. EHQ03 has a "Type of Employee" axis but only 3 coarse buckets. Adapter maps ISCO codes to bucket via leading digit; coarseness documented in two places. |
| 2 | Eurostat `earn_ses18_07` 404 (deprecated). | Probed half a dozen candidates; `earn_ses_annual` has the full `isco08` dim. |
| 3 | OECD `sdmx.oecd.org` returns 403 + Cloudflare HTML interstitial to anonymous httpx calls. Same wall on every endpoint under `/public/rest/`. | Adapter ships with content-type sniffing (returns empty when not `application/json`) and lives behind `enabled: false` in the preset. Documented as a P5 / follow-up problem. |
| 4 | ESCO `/api/search?type=occupation` pagination is broken past offset=100 — returns empty results. Same for `/api/resource/concept?isInScheme=...`. | Walked the ISCO concept tree from the 10 major groups via `narrowerConcept` / `narrowerOccupation`. 620 HTTP calls instead of 30, but it actually works. |
| 5 | Recurring numpy "cannot load module more than once per process" import error on Windows when running a single pytest file. | Goes away when running multiple test files together (test_runner pulls in the source modules first). P3 session log flagged this as a known issue. Workaround: clear `__pycache__` + run a broader pytest selection. |
| 6 | Initial test assertion in `test_parse_extracts_managers_bucket_for_2511` was wrong — I had the fixture's stride math inverted, expected the wrong cell. | Recomputed strides on paper, corrected the assertion. Now the test doubles as documentation of the JSON-stat flat-array layout. |
| 7 | mypy flagged `bucket = _isco_to_cso_bucket(...)` as reassigning a previously inferred `str` (from a prior loop's `for bucket in (...)`) to `str | None`. | Renamed the loop variable to `bucket_code`. |
| 8 | mypy: `adapter.fetch(cfg, rates=...)` failed because the `BenchmarkAdapter` Protocol didn't declare `rates`. | Added optional `rates` to the Protocol; CSO now accepts (and ignores) it; runner has a `TypeError` fallback for test-fixture adapters that don't accept it. |
| 9 | ESCO root URI `http://data.europa.eu/esco/isco/C` returned 404. | Seeded the BFS with the 10 major groups (`C0`–`C9`) directly. |

## External sources consulted

- CSO PxStat: `ws.cso.ie/public/api.restful/PxStat.Data.Cube_API.ReadDataset/{EHA05,EHQ03,NES01}/JSON-stat/2.0/en`
- OECD SDMX: `sdmx.oecd.org/public/rest/dataflow/all/all/latest`, `.../public/rest/data/OECD.ELS.SAE,DSD_EARNINGS@DF_EAR_MEI,1.0/all`
- Eurostat SDMX: `ec.europa.eu/eurostat/api/dissemination/sdmx/2.1/data/{earn_ses_annual, earn_ses_hourly, earn_ses_pub2s, earn_ses18_28, earn_ses18_07, earn_ses18_27}`
- ESCO REST API: `ec.europa.eu/esco/api/{search, resource/concept, resource/taxonomy}` — search/concept paginations confirmed broken, concept-tree walk confirmed working.

## Branch + commit state at session close

```
* p4-benchmarks-isco-hn  <this-commit>  docs(p4): adding-a-benchmark.md, CHANGELOG, session log
                         26488ef        feat(runner): benchmark fan-out + sibling parquet
                         7b21f85        feat(benchmarks): Eurostat SES adapter
                         249b2d4        feat(benchmarks): OECD SDMX-JSON adapter
                         ce7cd4d        feat(benchmarks): CSO PxStat (EHQ03) adapter
                         ce9bdb5        feat(benchmarks): shared helpers + throttle decision
                         27bd64f        feat(llm): stub interface
                         5e0c546        feat(normalise): wire ISCO tagger into pipeline
                         da2d8eb        feat(isco): rapidfuzz tagger + label loader
                         57076d2        feat(esco): static ISCO-08 label snapshot
                         7bae4f1        chore: dev dep group
                         230f787        pre: snapshot
  main                   bd25723        feat: P3 — ATS source adapters
```

No remote configured. Nothing pushed. Branch is ready for **squash-merge to `main`** (per the user's PR-shape choice across phases).

## Handover — start here next session

### Where we are
- `main` has P0+P1+P2+P3. `p4-benchmarks-isco-hn` has the benchmarks-and-ISCO slice in 12 commits; **not merged yet**.
- First action of the next session: squash-merge → `main`, then branch `p5-hn-algolia-llm` (or similar).

### Three follow-up PRs the deferred scope expects

1. **HN Algolia + LLM client** (the rest of the original P4 spec).
   - Implement the real OpenAI-compatible client behind `src/jobpipe/llm.py`. Honour `LLM_ENABLED` / `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`. Use `httpx` + `tenacity`. Cache prompts? Optional — first revision can be uncached.
   - Wire LLM fallback into `isco/tagger.py` for the `isco_match_method == "none"` rows. Track LLM-call count + dollar estimate in the run manifest. Gate at the tagger boundary so the no-LLM path stays the default.
   - Write `src/jobpipe/sources/hn_algolia.py`. Endpoint: `hn.algolia.com/api/v1/search?query=who+is+hiring&tags=story`, then for each thread fetch its comments. Each comment is free-text — extract title/company/salary via LLM. Skip the adapter entirely when `LLM_ENABLED=false` (rather than emit a useless empty frame).
   - Don't try a regex-based fallback for HN. The P3 scoping rejected that path explicitly.

2. **OECD unblock.**
   - Try options in order: (a) authenticated OECD API key in `OECD_API_KEY`, (b) `data.oecd.org` / `data-explorer.oecd.org` CSV mirror, (c) fixed-egress proxy. Adapter is already implemented; just need the egress fixed.
   - Flip `oecd.enabled: true` in the preset once a path works.

3. **P5: refresh.yml + Release upload.**
   - The daily cron workflow that runs `jobpipe fetch | normalise | publish`. Honour the per-source / per-benchmark `min_interval_hours` already in the preset.
   - Publish step should bundle `data/enriched/<latest>/postings.parquet` AND `benchmarks.parquet` (now that both exist) under a `latest` GitHub Release asset.

### Verification still owed

- **Live end-to-end smoke**: this PR runs the unit tests against fixtures only. A live `jobpipe fetch && jobpipe normalise` against the real APIs would catch any divergence between the fixture-built parsers and live responses. CSO + Eurostat should work today; OECD will be empty.
- **ISCO match rate on real data**: the 499-row P3 sample has every title tagged `None` because tagging didn't run then. After a real normalise pass we should record the actual coverage in the next session log — if it's <60% the LLM fallback PR moves up the priority list.

### Pitfalls / watch out for

- **Windows numpy import flake** (Issue #5). If pytest dies on a single-file run, clear `__pycache__` or run a wider selection.
- **CSO bucket coarseness leaks to the dashboard.** Every ISCO 1xxx/2xxx/3xxx row in `benchmarks.parquet` from CSO has the same `median_eur`. The dashboard should either show CSO at major-group resolution or stack it with a "umbrella bucket" badge.
- **Eurostat 4-year lag.** `period` carries the actual survey vintage ("2022"). Dashboard work should surface the lag explicitly instead of presenting it as "current."
- **OECD adapter is dormant code.** Easy to regress because nothing exercises it end-to-end. Keep the fixture tests passing; live verification is gated on the unblock PR.
- **Smoke-test benchmark assertion grows by one per phase.** When the LLM-enabled HN adapter lands, add it to `tests/test_smoke.py`'s source-registry assertion.
- **Per-adapter benchmark coverage is below the team-norm 90%.** Most uncovered lines are sparse-value JSON-stat branches. Add specific edge-case fixtures (sparse dict-value response, missing dim, malformed values) in the follow-up before sliding further.

### Quality gate commands (run before every commit)

```bash
uv run ruff check
uv run ruff format --check
uv run mypy --strict src/jobpipe
uv run pytest --cov=jobpipe --cov-branch --cov-fail-under=80
```
