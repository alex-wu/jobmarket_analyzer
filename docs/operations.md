# Operations runbook

Three loops keep this project shipping. Each one is independently runnable; together they cover everything from a fresh clone to a green deploy.

- [1. Local dev](#1-local-dev--work-on-the-dashboard-against-the-latest-dataset) — work against the latest dataset on your laptop.
- [2. Refresh on demand](#2-refresh-the-dataset-on-demand) — trigger a fresh pipeline run between scheduled crons.
- [3. Push site changes](#3-push-site-changes) — deploy the dashboard to GitHub Pages.

Post-2026-05-17 scope pivot: the pipeline is Adzuna-only and multi-preset. Each preset produces its own `latest-{preset_id}.parquet`. Default v1 preset is `data_analyst_eu`. See [ADR-017](../DECISIONS.md#adr-017--scope-cut-to-adzuna-only-post-v1-stabilisation) for rationale.

Local vs CI data path is unified: both read from `data/gh_databuild_samples/`. See [§4](#4-local-vs-ci-data-path) for why.

---

## 1. Local dev — work on the dashboard against the latest dataset

Prerequisites: Node 24+, [`gh`](https://cli.github.com/) authenticated against `alex-wu/jobmarket_analyzer` (or your fork). The `data/` directory is `.gitignore`d — a fresh clone has no Parquet on disk.

```powershell
# Pull the latest production parquet + manifest for the active preset.
# Replace data_analyst_eu with your preset_id if running a fork.
$preset = "data_analyst_eu"
gh release download "latest-$preset" `
  -p "latest-$preset.parquet" -p "manifest.json" `
  -R alex-wu/jobmarket_analyzer `
  -D data/gh_databuild_samples/ --clobber

# Start the Observable Framework dev server (hot reload at http://127.0.0.1:3000).
cd site
npm install
npm run dev
```

The page lives at <http://127.0.0.1:3000/>. Edits to `site/src/**` hot-reload. The preset switcher in the UI selects which `latest-{preset_id}.parquet` is active. The data loaders read from `data/gh_databuild_samples/` — refresh that directory whenever you want newer numbers.

### Running multiple presets locally

To pull every preset's accumulated dataset in one go:

```powershell
foreach ($preset in (Get-ChildItem config/runs -Filter "*.yaml" | Where-Object Name -notmatch "^_").BaseName) {
  gh release download "latest-$preset" `
    -p "latest-$preset.parquet" -p "manifest.json" `
    -R alex-wu/jobmarket_analyzer `
    -D data/gh_databuild_samples/ --clobber
}
```

(Skips the `_archived/` directory by filtering on names not starting with `_`.)

### Pre-push gate

Before committing anything under `site/**`:

```powershell
cd site
npm run build && npm run smoke
```

`npm run build` produces `site/dist/`. `npm run smoke` walks the dev server + the static build with headless Chromium and asserts zero runtime errors. **`npm run build` alone is not sufficient** — Framework doesn't execute cell JavaScript at build time ([[pitfall-duckdb-client-arrow-table]]).

`npm run smoke` accepts a `SMOKE_PHASE` env var:

- `all` (default) — dev server + dist (the local-dev case).
- `dev` — dev server only.
- `dist` — static `dist/` only (used by CI in `pages.yml`).

---

## 2. Refresh the dataset on demand

The weekly Monday 06:00 UTC cron runs `refresh.yml` automatically for every preset in the matrix. To trigger a refresh outside that window:

```powershell
# Refresh every preset in the matrix:
gh workflow run refresh.yml -R alex-wu/jobmarket_analyzer
gh run watch -R alex-wu/jobmarket_analyzer    # wait until green
```

`refresh.yml` triggers every preset in `strategy.matrix.preset` in parallel jobs. To limit to a single preset on a one-off basis, temporarily edit the matrix list on a branch and `--ref` to that branch (single-preset workflow_dispatch input is deferred until presets > 1).

For each preset in the matrix, `refresh.yml` fetches Adzuna across the preset's `countries`, normalises, ISCO-tags, then:

1. Uploads the run's snapshot to an immutable `data-{preset_id}-YYYY-MM-DD` dated release (idempotent per UTC day per preset).
2. Downloads the last 180 days of dated releases for the preset, unions them into the accumulated artifact.
3. Uploads `latest-{preset_id}.parquet` + `manifest.json` to the `latest-{preset_id}` release (re-clobbered).

The Pages site rebuilds automatically when **any** preset's `refresh.yml` job completes — `pages.yml`'s `workflow_run` trigger fires off the `refresh` workflow's success conclusion. Multiple matrix jobs completing in close succession may trigger multiple rebuilds; Pages handles the queueing.

**Manifest semantics:** `manifest.postings.row_count` measures the **fresh weekly fetch** — that is what `gate.min_total_rows` calibrates against (a weekly-fetch health check, not a corpus check). The shipped `latest-{preset_id}.parquet` is the much larger accumulated corpus; its size is recorded separately as `manifest.postings.accumulated_row_count` (with `accumulate_window_days`) after the accumulation rewrite.

**Failure alerting:** a red `refresh.yml` run files (or comments on) a GitHub issue titled `refresh failed: preset {preset_id}` via the workflow's final `if: failure()` step. Until fixed, the dashboard keeps serving the last good release — data goes stale, it does not break.

To pull the new data locally after a refresh, re-run the `gh release download` snippet from §1.

### Backfill / one-off accumulation

If `latest-{preset_id}` is corrupted or accidentally deleted, it can be recomputed from the dated archive. The full path requires a normal `fetch → normalise → publish` cycle plus the accumulation window override:

```powershell
$preset = "data_analyst_eu"
uv run jobpipe fetch     --preset config/runs/$preset.yaml
uv run jobpipe normalise --preset config/runs/$preset.yaml
# Download the archive window into data/archive/data-$preset-*/ first
# (see refresh.yml "Download accumulation window" step for the gh CLI pattern),
# then accumulate-on-publish:
uv run jobpipe publish   --preset config/runs/$preset.yaml --accumulate-window-days 180
```

A `--accumulate-only` flag that skips the fresh fetch is queued (see [[reference-phase-status]]) — useful when only the accumulation step needs re-running. Dated releases are immutable; the archive is the source of truth.

---

## 3. Push site changes

`pages.yml` deploys on push to `main` under `site/**`. Standard branch flow:

```powershell
git checkout -b feat/<short-name>
# … edits …
cd site
npm run build && npm run smoke    # gate
cd ..
git add site/                     # stage just the site changes
git commit -m "feat(site): <message>"
git push -u origin feat/<short-name>
gh pr create --fill --base main

# After review + green checks:
gh pr merge --squash --delete-branch
```

Merging to `main` triggers `pages.yml`. Live URL: <https://alex-wu.github.io/jobmarket_analyzer/>.

### Manual deploy (no code change)

If you want to re-deploy without pushing — e.g., to pick up a new dataset out-of-band of the refresh trigger:

```powershell
gh workflow run pages.yml -R alex-wu/jobmarket_analyzer
```

---

## 4. Local vs CI data path

Both environments read from `data/gh_databuild_samples/latest-{preset_id}.parquet`:

| | How the file arrives |
|---|---|
| **Local** | Developer runs `gh release download latest-{preset} …` from §1. |
| **CI** (`pages.yml`) | The workflow's "Download latest dataset from release" step downloads the single hardcoded preset's `latest-data_analyst_eu.parquet` (`PRESET_ID` env in `pages.yml`). Multi-preset enumeration is queued per ADR-019. |

The data loader does not branch on environment — single code path, identical bytes. If a refresh changes the schema, both environments break the same way at the same time, which is the point.

---

## 5. Triggers cheatsheet

| Trigger | What fires | Effect |
|---|---|---|
| Push to `main` under `site/**` | `pages.yml` | Rebuilds + deploys the dashboard. |
| `gh workflow run refresh.yml` | `refresh.yml` (matrix over presets) | Re-runs the pipeline for every preset; uploads new releases; chains to `pages.yml`. |
| Weekly Monday 06:00 UTC cron | `refresh.yml` | Same as above, automatic. |
| `gh workflow run pages.yml` | `pages.yml` | Manual deploy (no upstream change required). |
| Push to `main` (Python code) | `ci.yml` | Ruff / Mypy / pytest. Does NOT deploy. |

---

## 6. Rebuild the ESCO snapshots

Two static snapshots ship in `config/esco/`. Rebuild only when ESCO publishes a new minor version that the upstream mirrors pick up. Neither is part of the weekly refresh — the parquets are committed and consumed read-only by `normalise.run`.

### `isco08_labels.parquet` (occupation taxonomy, ADR-010)

```powershell
uv run python scripts/build_esco_snapshot.py
# Walks ESCO concept tree from the 10 ISCO major groups; emits ~2.1k labels.
# See `scripts/build_esco_snapshot.py` docstring + [[pitfall-esco-api]].
```

### `skills_labels.parquet` (Pillar B skills/knowledge, ADR-023)

```powershell
uv run python scripts/build_esco_skills_snapshot.py
# Downloads three CSVs from the tabiya-tech ESCO v1.1.1 mirror (~16 MB total)
# into `.cache/esco/`, joins skills × occupations × occupation_skill_relations,
# emits ~13.9k skills with related_isco_codes back to the parquet.
# Re-run forces re-download by `Remove-Item -Recurse .cache/esco/`.
```

After either rebuild: commit the regenerated parquet, bump notes in `DECISIONS.md` if the upstream ESCO version changed, and re-run `uv run pytest tests/skills tests/isco` to confirm the loaders still pass.

---

## 7. First-time setup

If you are setting up a fork (or this canonical repo for the first time):

1. Repo secrets — see [`docs/github-setup.md`](github-setup.md) §1 (`ADZUNA_APP_ID`, `ADZUNA_APP_KEY`; both required for v1 Adzuna-only pipeline).
2. Workflow permissions = Read and write — [`docs/github-setup.md`](github-setup.md) §2.
3. Pages source = GitHub Actions — [`docs/github-setup.md`](github-setup.md) §3.

Without (3), the first `pages.yml` run errors out with `Error: Pages site does not exist`.
