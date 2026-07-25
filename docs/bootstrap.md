# Bootstrap — start here

Single entry point for the next working session (human or AI agent) and for anyone picking the project up cold. Read this first; everything else is linked from here.

_Last updated: 2026-07-24._

---

## Read order

1. [README](../README.md) — what the project is, quick start, shipped/next summary.
2. [docs/architecture.md](architecture.md) — dataflow, module map, schemas, failure model.
3. [DECISIONS.md](../DECISIONS.md) — the *why* behind every locked choice (26 ADRs). Skim statuses; read in full any ADR touching the area you're changing.
4. [docs/open-questions.md](open-questions.md) — known limitations and the prioritised backlog. **This is the ops/quality work queue.**
5. [docs/feature-roadmap.md](feature-roadmap.md) — BI + AI feature track (new user-facing capability), with hard constraints and per-feature acceptance criteria.
6. [docs/operations.md](operations.md) — day-to-day runbooks (local dev, refresh, deploy, ESCO snapshot rebuilds).
7. When touching CI or repo settings: [docs/ci-cd-practices.md](ci-cd-practices.md) + [docs/github-setup.md](github-setup.md).
8. When touching the Adzuna adapter: [docs/references/adzuna_api.md](references/adzuna_api.md) — empirical response-shape notes + ToS constraints.

## State snapshot (2026-07-24)

- `main` is the only long-lived branch; everything ships through squash-merged PRs (merge commits are rejected by branch protection).
- End-to-end automation is live and unattended: Monday 06:00 UTC cron (`refresh.yml`) → fetch/normalise/publish/gate → dated + `latest-data_analyst_eu` releases → Pages rebuild via `workflow_run`. A red run files a `refresh failed: preset {id}` GitHub issue.
- Weekly cron has run green since 2026-06-08. Pipeline hardening (credential scrubbing, real retry semantics, NaT quarantine, failure alerting) merged 2026-07-21 — **the 2026-07-27 run is the first with the hardened code.**
- Dashboard: 8 pages (Overview, Trends, Geography, Work Arrangement, Skills & Roles, Compare Periods, Quality & Coverage, Methodology), live on GitHub Pages. Firefox is the recommended browser (upstream duckdb-wasm #1658 affects Chromium-on-Windows).
- Schema v3; active preset `config/runs/data_analyst_eu.yaml` (gb + es, weekly, 180-day accumulation window).

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

Ops/quality items with context in [open-questions.md](open-questions.md); new-feature track (Trends page, AI features) in [feature-roadmap.md](feature-roadmap.md). Suggested ops order:

1. **Adzuna attribution footer** — smallest task, ToS hygiene. The site footer currently reads "Data: Adzuna"; Adzuna's terms want attribution as "The Adzuna API" + link. One edit in `site/observablehq.config.js`.
2. **Gate calibration** — `min_total_rows: 80` is still a guess; ground it against the fresh-delta `row_count` of the published weekly manifests (7+ exist).
3. **Artifact correctness gate** — post-publish validation of the released parquet + manifest.
4. **`raw_payload` keep/drop** — full upstream JSON ships in the public parquet; size + ToS surface.
5. **PR-gate smoke for `site/**`** — the headless smoke only runs on push to `main` today.
6. **Preset switcher** (larger) — loader pins `data_analyst_eu`; enumeration per ADR-019.

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
