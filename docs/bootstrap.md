# Bootstrap — start here

Single entry point for the next working session (human or AI agent) and for anyone picking the project up cold. Read this first; everything else is linked from here.

_Last updated: 2026-09-13._

---

## Read order

1. [README](../README.md) — what the project is, quick start, shipped/next summary.
2. [docs/architecture.md](architecture.md) — dataflow, module map, schemas, failure model.
3. [DECISIONS.md](../DECISIONS.md) — the *why* behind every locked choice (26 ADRs). Skim statuses; read in full any ADR touching the area you're changing.
4. [docs/open-questions.md](open-questions.md) — known limitations and the prioritised backlog. **This is the ops/quality work queue.**
5. [docs/feature-roadmap.md](feature-roadmap.md) — BI + AI feature track (new user-facing capability), with hard constraints and per-feature acceptance criteria.
6. [docs/portfolio-audit.md](portfolio-audit.md) — **the priority order.** Every roadmap + ops item ranked by value/effort/complexity for a reviewer, with a standout checklist and a three-sprint sequence. Pick the top unshipped item there.
7. [docs/operations.md](operations.md) — day-to-day runbooks (local dev, refresh, deploy, ESCO snapshot rebuilds).
8. When touching CI or repo settings: [docs/ci-cd-practices.md](ci-cd-practices.md) + [docs/github-setup.md](github-setup.md).
9. When touching the Adzuna adapter: [docs/references/adzuna_api.md](references/adzuna_api.md) — empirical response-shape notes + ToS constraints.

## State snapshot (2026-09-14)

- `main` is the only long-lived branch; everything ships through squash-merged PRs (merge commits are rejected by branch protection).
- End-to-end automation is live and unattended: Monday 06:00 UTC cron (`refresh.yml`) → fetch/normalise/publish/gate → dated + `latest-data_analyst_eu` releases → Pages rebuild via `workflow_run`. A red run files a `refresh failed: preset {id}` GitHub issue.
- Weekly cron green every week since 2026-06-08; latest run 2026-09-14 (18 dated releases). The hardened pipeline (PR #33) has now run 8 times without incident; no `refresh failed:` issues exist. Latest manifest: schema v3, `row_count` 1,001 fresh / `accumulated_row_count` 5,847 over 180 days, ISCO fuzzy 550 / none 451 (55%).
- Dashboard: 8 pages (Overview, Trends, Geography, Work Arrangement, Skills & Roles, Compare Periods, Quality & Coverage, Methodology), live on GitHub Pages. Firefox is the recommended browser (upstream duckdb-wasm #1658 affects Chromium-on-Windows). Trends (F1) shipped 2026-07-25 via PR #37.
- **F2 shipped 2026-09-14** on `feat/market-pulse-overview` (unpushed, no PR yet): shared `deltaSub` component, Overview "Market pulse" strip (latest complete week vs prior), plus a fix for snapshot counts that compared accumulated rows to the fresh weekly `row_count`. Branch also carries the 2026-09-13 docs commits. **Next: open the PR and squash-merge to close the 7-week branch.**
- 2026-09-13 audit: local gate green (ruff, format, mypy strict, 374 pytest); docs re-aligned with code (README page count, `llm.py` cutoff docstring); [portfolio-audit.md](portfolio-audit.md) added as the priority order.
- Schema v3; active preset `config/runs/data_analyst_eu.yaml` (gb + es, weekly, 180-day accumulation window). `gate.min_total_rows: 80` still uncalibrated against the 17 real manifests.

## First checks for the next session

Verify the most recent Monday cron before building anything on top of it:

```bash
gh run list --workflow=refresh.yml --limit 1          # expect: completed / success
gh release download latest-data_analyst_eu -p manifest.json -D /tmp/check --clobber
# expect manifest.postings to carry: schema_version "3", row_count (fresh delta),
# accumulated_row_count + accumulate_window_days (added 2026-07-21)
```

If the run is red, a `refresh failed:` issue should already exist — start there.

## Prioritised backlog

**Authoritative order: [portfolio-audit.md](portfolio-audit.md)** (ranked #1–#18 by value/effort for a reviewer). Detail lives in [open-questions.md](open-questions.md) (ops/quality) and [feature-roadmap.md](feature-roadmap.md) (F-numbered features). Sprint A, in order:

1. **#1 README hero + repo metadata** — screenshot/GIF, 3-line pitch, live link above fold, inline architecture diagram; fix the GitHub repo description (still says "overlay official salary benchmarks" — shelved by ADR-017) and add topics.
2. **#2 Widen preset to 7 countries** — `countries: [gb, de, fr, nl, es, it, pl]` in `data_analyst_eu.yaml`; raise `max_results`; recalibrate `gate.min_total_rows` from the 17 real manifests. Let one Monday cron run before building insight pages on it.
3. ~~**#4 Finish F2**~~ — shipped 2026-09-14; only the PR + squash-merge remain.
4. **#14 Adzuna attribution footer** — footer reads "Data: Adzuna"; terms want "The Adzuna API" + link. One edit in `site/observablehq.config.js`.

Then Sprint B (#3 findings page, #5 posting lifetime, #6 AI brief, #9 Chrome retry) — see the audit.

## Working conventions (the ones that bite)

- **Run the full gate locally before any PR push** — CI runs lint/format/types *before* tests, so green pytest alone is not green CI:
  ```bash
  uv run ruff check . && uv run ruff format --check . && uv run mypy --strict src/jobpipe && uv run pytest -q
  ```
- **Site changes:** `cd site && npm run build && npm run smoke`. `npm run build` alone is insufficient (cell JS doesn't execute at build time). `site/scripts/smoke.mjs` has a **hardcoded page list** (`DATA_PAGES`) — adding a dashboard page means adding it there too.
- Squash-merge only; conventional-commit prefixes; no force-push to `main`. See [CONTRIBUTING.md](../CONTRIBUTING.md).
- Windows dev quirk: single-file pytest runs can hit a numpy re-import error — clear `__pycache__` and run a broader selection (documented in CONTRIBUTING).
- Postings `country` values are UPPERCASE ISO2 (`GB`/`ES`) while preset YAML and Adzuna URLs use lowercase — normalise case on any new join (this silently emptied the first choropleth).

## Keeping this file useful

Update the snapshot date and backlog when they drift; keep it one page. Detailed history belongs in [CHANGELOG.md](../CHANGELOG.md), rationale in [DECISIONS.md](../DECISIONS.md), runbooks in [operations.md](operations.md) — link, don't duplicate.
