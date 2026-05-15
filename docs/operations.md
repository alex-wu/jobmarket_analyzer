# Operations runbook

Three loops keep this project shipping. Each one is independently runnable; together they cover everything from a fresh clone to a green deploy.

- [1. Local dev](#1-local-dev--work-on-the-dashboard-against-the-latest-dataset) — work against the latest dataset on your laptop.
- [2. Refresh on demand](#2-refresh-the-dataset-on-demand) — trigger a fresh pipeline run between scheduled crons.
- [3. Push site changes](#3-push-site-changes) — deploy the dashboard to GitHub Pages.

Local vs CI data path is unified: both read from `data/gh_databuild_samples/`. See [§4](#local-vs-ci-data-path) for why.

---

## 1. Local dev — work on the dashboard against the latest dataset

Prerequisites: Node 20+, [`gh`](https://cli.github.com/) authenticated against `alex-wu/jobmarket_analyzer` (or your fork). The `data/` directory is `.gitignore`d — a fresh clone has no Parquet on disk.

```powershell
# Pull the latest production parquet + manifest into the local data dir.
gh release download latest `
  -p "postings__postings.parquet" -p "manifest.json" `
  -R alex-wu/jobmarket_analyzer `
  -D data/gh_databuild_samples/ --clobber

# Start the Observable Framework dev server (hot reload at http://127.0.0.1:3000).
cd site
npm install
npm run dev
```

The page lives at <http://127.0.0.1:3000/>. Edits to `site/src/**` hot-reload. The data loaders (`site/src/data/postings.parquet.js`, `manifest.json.js`) read from `data/gh_databuild_samples/` — refresh that directory whenever you want newer numbers.

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

The daily 06:00 UTC cron runs `refresh.yml` automatically. To trigger a refresh outside that window:

```powershell
gh workflow run refresh.yml -R alex-wu/jobmarket_analyzer
gh run watch -R alex-wu/jobmarket_analyzer    # wait until green
```

`refresh.yml` fetches all sources (Adzuna + 4 ATS adapters), normalises, ISCO-tags, then uploads:

- `postings__postings.parquet` + `manifest.json` to the `latest` release (re-clobbered).
- The same files to an immutable `data-YYYY-MM-DD` dated release (idempotent per UTC day).

The Pages site rebuilds automatically when `refresh.yml` completes — `pages.yml`'s `workflow_run` trigger fires off the `refresh` workflow's success conclusion.

To pull the new data locally after a refresh, re-run the `gh release download` snippet from §1.

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

Both environments read from `data/gh_databuild_samples/postings__postings.parquet`:

| | How the file arrives |
|---|---|
| **Local** | Developer runs `gh release download latest …` from §1. |
| **CI** (`pages.yml`) | The workflow's "Download latest dataset from release" step runs the same `gh release download` flags. |

The data loader at `site/src/data/postings.parquet.js` does not branch on environment — single code path, identical bytes. If a refresh changes the schema, both environments break the same way at the same time, which is the point.

---

## 5. Triggers cheatsheet

| Trigger | What fires | Effect |
|---|---|---|
| Push to `main` under `site/**` | `pages.yml` | Rebuilds + deploys the dashboard. |
| `gh workflow run refresh.yml` | `refresh.yml` | Re-runs the pipeline; uploads new release; chains to `pages.yml`. |
| Daily 06:00 UTC cron | `refresh.yml` | Same as above, automatic. |
| `gh workflow run pages.yml` | `pages.yml` | Manual deploy (no upstream change required). |
| Push to `main` (Python code) | `ci.yml` | Ruff / Mypy / pytest. Does NOT deploy. |

---

## 6. First-time setup

If you are setting up a fork (or this canonical repo for the first time):

1. Repo secrets — see [`docs/github-setup.md`](github-setup.md) §1 (`ADZUNA_APP_ID`, `ADZUNA_APP_KEY`; both optional).
2. Workflow permissions = Read and write — [`docs/github-setup.md`](github-setup.md) §2.
3. Pages source = GitHub Actions — [`docs/github-setup.md`](github-setup.md) §3.

Without (3), the first `pages.yml` run errors out with `Error: Pages site does not exist`.
