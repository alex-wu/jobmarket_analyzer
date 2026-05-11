# Session log — 2026-05-11 · Bootstrap + P0 + P1

> First session. Repo was a greenfield prototype with two markdown files and no git. Closed the session with P0 scaffolding merged on `main` and P1 (Adzuna adapter + preset runner) committed on `p1-adzuna-source`.

## Premise

User brief (condensed from the opening message):

- Portfolio project hosted on **GitHub Pages**. Interactive salary-distribution dashboard with filters and slices. v1 starts with **data-analyst roles**, expand later.
- Pull from **free APIs**, clean/dedupe/standardise into a database file, then a **BI framework** consumes it for the dashboard.
- **Every data point must link back** to its source posting URL (for verification).
- Daily or weekly refresh acceptable — open on whether Dagster, GitHub Actions, or other.
- **Public OSS** so others can fork and use, not just a personal portfolio piece.
- Strong preference for **active FOSS libraries** over custom code; surface unrealistic architectural choices.
- Git-centric workflow: initialise first, branches before changes.

User later clarified:
- Scope: **Ireland / Eurozone** (not US).
- Architecture must be **pluggable** so other roles/industries can be added without code changes — no hardcoded employer lists in source files; that scoping belongs in YAML.

## Plan

**Plan file:** `~/.claude/plans/i-want-to-create-polymorphic-quokka.md` (persistent on the user's local Claude install; mirror summary below in case it disappears).

**Locked architectural decisions** (canonical: `DECISIONS.md`):

| Concern | Choice |
|---|---|
| Orchestration | GitHub Actions cron (not Dagster) |
| Frontend | Observable Framework + DuckDB-WASM |
| Storage | DuckDB + partitioned Parquet, hosted via GitHub Releases as CDN |
| Sources | Adzuna + Greenhouse + Lever + Ashby + Personio + Remotive + HN Algolia |
| Benchmarks | CSO PxStat (IE) + OECD SDMX + Eurostat |
| Occupation taxonomy | ESCO (ISCO-08 4-digit) |
| Licence | Apache-2.0 |
| Env mgr | `uv` (Python 3.12) |
| LLM | Optional; pipeline materialises end-to-end with `LLM_ENABLED=false` |
| Excluded sources | JobSpy (Indeed/LinkedIn block GH Actions datacenter IPs) |

**Phase plan** (current state in `README.md` and the table below — keep in sync):

- [x] **P0** — Scaffolding, git init, CI green
- [x] **P1** — Adzuna source adapter + raw Parquet
- [ ] **P2** — Normalisation + dedupe + strict `PostingSchema`
- [ ] **P3** — ATS + community source adapters (Greenhouse, Lever, Ashby, Personio, Remotive, HN Algolia)
- [ ] **P4** — Benchmark adapters + ESCO/ISCO tagging
- [ ] **P5** — GH Actions refresh.yml + Release upload
- [ ] **P6** — Observable Framework site + GH Pages deploy
- [ ] **P7** — Polish, second preset (`software_engineer_berlin.yaml`), screenshots

## What landed

### P0 (commit `f9ec129` on `main`)

- Apache-2.0 `LICENSE`, `README.md`, `CONTRIBUTING.md`, `DECISIONS.md` (8 ADRs), `NOTICE.md`, `CHANGELOG.md`, project `CLAUDE.md`.
- `pyproject.toml` uv-managed (Python 3.12, strict mypy, ruff, ≥80% coverage gate).
- `SourceAdapter` + `BenchmarkAdapter` Protocols + registry decorators (no concrete adapters yet).
- `PostingSchema` + `BenchmarkSchema` (pandera, `strict=False` until P2).
- Typer CLI skeleton: `jobpipe fetch | normalise | publish`.
- `pydantic-settings` config (`.env.example` catalogues vars).
- v1 preset `config/runs/data_analyst_ireland.yaml` with all sources disabled (per-phase activation).
- `.github/workflows/ci.yml` (lint + typecheck + tests + licence audit).
- `.pre-commit-config.yaml` (ruff, ruff-format, mypy, end-of-file fixer).
- `tests/test_license_audit.py` rejects `dlthub`, `dagster-cloud`, paid scrapers.
- Architecture diagram `docs/architecture.md` (mermaid).
- Original Dagster-centric `Project_Objectives.md` archived under `docs/history/` with superseded banner.

### P1 (commit `636164a` on `p1-adzuna-source`)

- `src/jobpipe/sources/adzuna.py` — paginated fetch against `api.adzuna.com/v1/api/jobs/{country}/search/{page}`. `AdzunaConfig` extends `SourceConfig` (`results_per_page`, `max_pages`, `timeout_seconds`, `min_interval_hours`). HTTP retries via `tenacity` (exponential backoff, 3 attempts, transient `httpx.HTTPError` only). Failures surface as typed `SourceFetchError`. Dependency-injected `httpx.Client` for testability.
- `src/jobpipe/runner.py` — `load_preset` (raises `PresetError` on malformed YAML), `fetch_sources` (fail-isolated fan-out + `PostingSchema.validate(lazy=True)`), `write_raw_parquet` (writes `data/raw/<preset>__<run_id>/postings_raw.parquet`), `run_fetch` (CLI entry point). `EmptyRunError` raised when zero rows across all enabled sources.
- `src/jobpipe/cli.py` — `jobpipe fetch` wired to runner. `--verbose` flag. Exit code 2 on `PresetError` / `EmptyRunError`.
- Preset enabled adzuna with country `["gb"]` (English-language labour-market proxy; documented inline why Adzuna doesn't serve `ie`).
- Tests: 40 pass; coverage 95.51%. `tests/sources/test_adzuna.py` uses synthetic JSON fixtures + `httpx.MockTransport`. `tests/test_runner.py` covers preset error paths, fail-isolation, end-to-end Parquet write.
- README phase-checkbox + CHANGELOG entry.

## Issues + resolutions

| # | Encountered | Resolution |
|---|---|---|
| 1 | `git commit` failed initially with no identity. | Set repo-local (not global) `user.email` / `user.name`. User's global CLAUDE.md says never update *the* git config — local-only on fresh-init was the conservative interpretation. |
| 2 | Initial scope drift around Ireland-laser focus → almost ended up suggesting 30–50 hardcoded employer slugs in Python source. | User pushed back; reframed around pluggable adapters + YAML scoping. Saved as a `feedback` memory so future sessions don't repeat the mistake. |
| 3 | Adzuna **does not serve Ireland** (`ie`) in 2026 — confirmed during P1 web research. | Preset enabled with `["gb"]` as adjacent labour-market proxy; documented inline in the preset YAML. Real IE coverage comes in P3 via ATS adapters. |
| 4 | Adzuna **does not publicly document free-tier rate limits** in their dev portal. | Conservative defaults baked in (`max_pages=5 × results_per_page=50 = 250 results per fetch`) + `min_interval_hours=24` config knob. Refresh workflow in P5 will honour this. |
| 5 | Mypy strict failed on `dict[str, object]` passed to `httpx.Client.get(params=...)`. | Typed `params: dict[str, str \| int]` explicitly. |
| 6 | Initial pytest coverage came in at 75% (gate 80%). | Added registry + CLI invocation tests to cover untested paths. Now 95.51%. |
| 7 | Ruff `RUF002` flagged the `∪` UNION character in `normalise.py` docstring as ambiguous. | Replaced with " or ". Same for unused `# noqa: B008` after ruff caught up with the typer pattern. |
| 8 | P0 smoke tests in `test_smoke.py` baked in P0-shaped assumptions (`registry == []`, `fetch` returns exit 0 with stub message). | Updated to P1 reality: `adzuna` is now registered, and `fetch` exits 2 on a missing preset. Future phase transitions will need similar smoke-test refresh — flag in handover. |

## External sources consulted

Research conducted via WebFetch / WebSearch during the planning phase. Future sessions can re-fetch if context is needed.

- **Observable Framework**: <https://github.com/observablehq/framework>, <https://duckdb.org/docs/current/clients/wasm/deploying_duckdb_wasm>
- **DuckDB-WASM + Cloudflare R2 patterns**: <https://andrewpwheeler.com/2025/06/29/using-duckdb-wasm-cloudflare-r2-to-host-and-query-big-data-for-almost-free/>
- **stlite (Streamlit-in-WASM)**: <https://github.com/whitphx/stlite/releases>
- **Quarto dashboards**: <https://quarto.org/docs/dashboards/deployment.html>
- **Adzuna developer portal**: <https://developer.adzuna.com/docs/search>, <https://developer.adzuna.com/overview>
- **USAJobs (out of v1 scope but referenced)**: <https://developer.usajobs.gov/>
- **Greenhouse/Lever/Ashby/Personio ATS APIs**: <https://developers.greenhouse.io/job-board.html>, <https://developers.ashbyhq.com/docs/public-job-posting-api>
- **HN Algolia search**: <https://hn.algolia.com/api>, <https://cotera.co/articles/hacker-news-api-guide>
- **Remotive remote-jobs API**: <https://remotive.com/remote-jobs/api>, <https://github.com/remotive-com/remote-jobs-api>
- **Eurostat / CSO Ireland (benchmarks)**: <https://data.cso.ie>, <https://ec.europa.eu/eurostat/web/labour-market/database>
- **OECD SDMX**: <https://data-explorer.oecd.org/>
- **ESCO taxonomy**: <https://esco.ec.europa.eu/en/use-esco/use-esco-services-api>, <https://esco.ec.europa.eu/en/use-esco/download>
- **LinkedIn scraping landscape 2026** (why we exclude it): <https://scrapfly.io/blog/posts/how-to-scrape-linkedin>

## Branch + commit state at session close

```
* p1-adzuna-source  636164a feat: Adzuna source adapter + preset runner (P1)
  main              f9ec129 init: scaffolding (P0)
                    bf38b76 pre: snapshot existing docs before P0 scaffolding
```

No remote configured. Nothing pushed. `p1-adzuna-source` is ready for merge to `main` (squash or fast-forward — user's call).

## Handover — start here next session

### Where we are
- `main` has P0 scaffolding. `p1-adzuna-source` has P1 work, all gates green, **not merged yet**.
- First action of the next session: decide on merge strategy with the user, merge `p1-adzuna-source` → `main`, then branch `p2-normalise`.

### Next phase: P2 — Normalisation + dedupe + strict schema

Acceptance criterion from the plan:
> `jobpipe normalise` produces a strict-valid `postings.parquet`; dedupe collapses obvious duplicates in fixtures; coverage ≥ 80% on `normalise.py`.

Concrete steps:
1. `src/jobpipe/fx.py` — pull ECB daily reference rates CSV (single small file, cached locally). Convert `salary_min_eur` / `salary_max_eur` from the *source currency* to EUR (Adzuna returns GBP for `gb`, etc.). NB: P1's Adzuna adapter leaves salary fields in **native currency** despite the field name suffix `_eur` — comment in `_normalise_row` flags this. P2 must do the conversion *and* fix the misleading field semantics by populating after FX.
2. Period normalisation in `src/jobpipe/normalise.py` — hourly × 2080, monthly × 12, etc. Populate `salary_annual_eur_p50` after FX.
3. Dedupe in `src/jobpipe/dedupe.py` — sha1 of normalised URL, fallback to sha1 of `title+company+country`. Re-running the same preset on the same day must not duplicate rows.
4. `src/jobpipe/schemas.py` — flip `PostingSchema.Config.strict = True`. Verify all adapters still pass.
5. `jobpipe normalise` CLI command wired to `normalise.run()` against the latest `data/raw/<preset>__*/postings_raw.parquet`.
6. Tests: parametrised FX (GBP/USD/EUR), period conversions, dedupe edge cases, integration test that runs `fetch` then `normalise`.

### Verification still owed (carried over from earlier memory)

- **Remotive ToS**: re-read at P3 start. Confirm attribution-in-dashboard-footer + `NOTICE.md` line is sufficient. If their terms now forbid commercial / public redistribution of the data, drop Remotive.
- **ESCO local API replacement**: ESCO's downloadable local API is flagged "to be replaced" in their docs. Check status at P4 start (<https://esco.ec.europa.eu/en/use-esco/use-esco-services-api>). Fallback: commit a static `config/esco/isco08_labels.parquet` snapshot and refresh quarterly.
- **Adzuna free tier**: resolved (no public limit documented; conservative defaults set). No further action needed unless real-world usage hits a wall.

### Pitfalls / watch out for

- **Each phase transition stales the smoke tests** in `tests/test_smoke.py` that bake in registry contents and CLI behaviour. Update them as part of each phase commit, not as a separate fix-up later.
- **The user's global CLAUDE.md enforces `pre: snapshot` commits before risky edits.** Honour it — don't batch risky edits into a single commit.
- **Mypy strict catches typed-dict / `dict[str, object]` issues at the httpx boundary.** Pre-emptively type request param dicts as `dict[str, str | int]` (or narrower) when adding new adapters.
- **Adzuna `_normalise_row` currently puts native-currency salary in `*_eur` fields** — P2 must fix this. The field name lies until FX runs. Don't ship P2 without addressing.
- **Adzuna doesn't serve Ireland.** Don't try to "fix" the preset by adding `ie` back; it'll just 404. IE coverage is intentionally deferred to ATS adapters in P3.
- **Dagster, JobSpy, BLS OEWS, US focus** all appear in the archived spec under `docs/history/` — they're explicitly *out of scope*. If a future task mentions any of them, push back and check `DECISIONS.md` ADR-001/003 first.

### Quality gate commands (run before every commit)

```
uv run ruff check
uv run ruff format --check
uv run mypy --strict src/jobpipe
uv run pytest --cov=jobpipe --cov-branch --cov-fail-under=80
```
