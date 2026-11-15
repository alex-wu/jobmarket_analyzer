# Bootstrap — start here

Single entry point for the next working session (human or AI agent) and for anyone picking the project up cold. Read this first; everything else is linked from here.

_Last updated: 2026-11-15._

---

## Read order

1. [README](../README.md) — what the project is, quick start, shipped/next summary.
2. [docs/architecture.md](architecture.md) — dataflow, module map, schemas, failure model.
3. [DECISIONS.md](../DECISIONS.md) — the *why* behind every locked choice (29 ADRs). Skim statuses; read in full any ADR touching the area you're changing.
4. [docs/open-questions.md](open-questions.md) — known limitations and the prioritised backlog. **This is the ops/quality work queue.**
5. [docs/feature-roadmap.md](feature-roadmap.md) — BI + AI feature track (new user-facing capability), with hard constraints and per-feature acceptance criteria.
6. [docs/portfolio-audit.md](portfolio-audit.md) — **the priority order.** Every roadmap + ops item ranked by value/effort/complexity for a reviewer, with a standout checklist and a three-sprint sequence. Pick the top unshipped item there.
7. [docs/operations.md](operations.md) — day-to-day runbooks (local dev, refresh, deploy, ESCO snapshot rebuilds).
8. When touching CI or repo settings: [docs/ci-cd-practices.md](ci-cd-practices.md) + [docs/github-setup.md](github-setup.md).
9. When touching the Adzuna adapter: [docs/references/adzuna_api.md](references/adzuna_api.md) — empirical response-shape notes + ToS constraints.

## State snapshot (2026-11-15)

- `main` is the only long-lived branch; everything ships through squash-merged PRs (merge commits are rejected by branch protection).
- End-to-end automation is live and unattended: Monday 06:00 UTC cron (`refresh.yml`) → fetch/normalise/publish/gate → dated + `latest-data_analyst_eu` releases → Pages rebuild via `workflow_run`. A red run files a `refresh failed: preset {id}` GitHub issue. Cron green every week since 2026-06-08; latest run 2026-11-09. No open issues.
- Dashboard: **9 pages** (Overview, Trends, Salary Distribution, Geography, Work Arrangement, Skills & Roles, Compare Periods, Quality & Coverage, Methodology), live on GitHub Pages.
- **Merged 2026-11-15:**
  - **SQLite browser engine** (ADR-027, PR #69). In-browser SQL runs on SQLite (sql.js); DuckDB stays in the pipeline and the build-time loader. The loader ran on CI's Node 24 and the Pages deploy succeeded.
  - **Salary Distribution page + chip filter bar** (ADR-028). Raincloud chart: every salaried posting is a hoverable, clickable dot. Chip filters (`components/chipFilters.js` + `chips.css`) exist on this page only, with a new skill filter (`skill=` URL parameter).
  - **Salary floor** (ADR-029). `normalise.salary_floor_eur: 10000` blanks day/hour/month rates that Adzuna reports without a pay period. Applied at normalise and at accumulation.
  - **Wording:** "imputed" is shown as "Estimated by Adzuna" vs "Stated in ad"; the column is still `salary_imputed` (Adzuna's `salary_is_predicted`).
- **The live data still contains below-floor salaries until the next `refresh.yml` run** (Monday cron, or a manual dispatch). The first run after the merge is the first real exercise of the floor in CI — check its log for the `salary floor: blanked N of M` line and that the manifest still passes the gate.
- **PR #50 (`feat/readme-hero-attribution`) is still open** and now conflicts in `README.md` (page count and the shipped-features bullet changed on `main`). Merge `origin/main` into it, re-run `npm run screenshots`, then merge.
- **PR #63 (Dependabot, `@duckdb/node-api` 2.x)** is open and not auto-mergeable: the loader depends on it. Run `npm run parity` on that branch before merging.
- Schema v3; active preset `config/runs/data_analyst_eu.yaml` (gb + es, weekly, 180-day accumulation window). `gate.min_total_rows: 80` is still uncalibrated against the real manifests.
- Local gate at this snapshot: ruff, format, mypy strict, 379 pytest (89% coverage); site build, parity 84/84, dist smoke 0 issues on Chrome and Firefox.

## First checks for the next session

Verify the most recent Monday cron before building anything on top of it:

```bash
gh run list --workflow=refresh.yml --limit 1          # expect: completed / success
gh release download latest-data_analyst_eu -p manifest.json -D /tmp/check --clobber
# expect manifest.postings to carry: schema_version "3", row_count (fresh delta),
# accumulated_row_count + accumulate_window_days
gh run view --log $(gh run list --workflow=refresh.yml --limit 1 --json databaseId --jq '.[0].databaseId') | grep "salary floor"
# expect after the first post-ADR-029 run: "salary floor: blanked N of M salaries below EUR 10,000 per year"
```

If the run is red, a `refresh failed:` issue should already exist — start there.

Then refresh the local sample so the dev server matches production (see "Refresh the local sample" on the Methodology page / [operations.md](operations.md)); the copy on the 2026-11-15 dev machine was cleaned by hand with the floor.

## Prioritised backlog

**Authoritative order: [portfolio-audit.md](portfolio-audit.md)** (ranked by value/effort for a reviewer). Detail lives in [open-questions.md](open-questions.md) (ops/quality) and [feature-roadmap.md](feature-roadmap.md) (F-numbered features). Next, in order:

1. **Land PR #50** — README hero + Adzuna attribution footer (audit #1, #14). Add a Salary Distribution screenshot while regenerating images.
2. **Roll the chip filter bar out to the other six filtered pages** (ADR-028 follow-up). Swap `filterCard` for `chipFilterBar`, set `style: chips.css` in `observablehq.config.js` instead of per page, delete `filterCard.js`, and update the smoke test's "first select = country" interaction check. Until then two filter UIs coexist and the other pages ignore `skill=`.
3. **Salary data quality** (surfaced by the new page; see open-questions "Salary quality"): `salary_min = 0` halving the midpoint, the default 250k salary-max filter hiding the top postings, "disclosed" wording that counts Adzuna estimates, a suspicious ~€46k cluster.
4. **#2 Widen preset to 7 countries** — `countries: [gb, de, fr, nl, es, it, pl]`; raise `max_results`; recalibrate `gate.min_total_rows`; re-check that 10,000 is a sensible salary floor for the new markets. Let one Monday cron run before building insight pages on it.
5. Then Sprint B in the audit (#3 findings page, #5 posting lifetime, #6 AI brief).

## Working conventions (the ones that bite)

- **Run the full gate locally before any PR push** — CI runs lint/format/types *before* tests, so green pytest alone is not green CI:
  ```bash
  uv run ruff check . && uv run ruff format --check . && uv run mypy --strict src/jobpipe && uv run pytest -q
  ```
- **Site changes:** `cd site && npm run clean && npm run build && npm run parity && SMOKE_PHASE=dist npm run smoke` (add `SMOKE_BROWSER=firefox` for a second engine). `npm run build` alone is insufficient (cell JS doesn't execute at build time); `npm run clean` matters after the sample parquet changes (the loader cache goes stale). `site/scripts/smoke.mjs` has a **hardcoded page list** (`DATA_PAGES` and the CSV list) — adding a dashboard page means adding it there too. After a Puppeteer bump: `npx puppeteer browsers install chrome` (and `firefox`).
- **Python gate must install extras:** `uv sync --frozen --all-extras` (ruff, mypy and pytest live in the `dev` extra, not the default group). On Windows, VS Code's Ruff language server locks `.venv/Scripts/ruff.exe` and makes `uv sync` fail half-way — restart the Ruff server (or close the editor) and sync again.
- **Browser SQL is SQLite** (ADR-027): portable SQL only — no `::` casts, `date_trunc`, `unnest` or typed literals; new date/boolean result columns go in the conversion lists in `site/src/components/db.js`.
- **Custom CSS is limited to `site/src/chips.css`** (ADR-028). Everything else stays on stock Framework / Plot / Inputs defaults.
- **Plot gotcha:** a channel named `title` replaces the whole hover tip; name it something else and label it.
- Squash-merge only; conventional-commit prefixes; no force-push to `main`. See [CONTRIBUTING.md](../CONTRIBUTING.md).
- Windows dev quirk: single-file pytest runs can hit a numpy re-import error — clear `__pycache__` and run a broader selection (documented in CONTRIBUTING).
- Postings `country` values are UPPERCASE ISO2 (`GB`/`ES`) while preset YAML and Adzuna URLs use lowercase — normalise case on any new join (this silently emptied the first choropleth).

## Keeping this file useful

Update the snapshot date and backlog when they drift; keep it one page. Detailed history belongs in [CHANGELOG.md](../CHANGELOG.md), rationale in [DECISIONS.md](../DECISIONS.md), runbooks in [operations.md](operations.md) — link, don't duplicate.
