# jobmarket_analyzer

> Modular, free-tier job-market intelligence pipeline. Weekly Adzuna ingest across the EU, normalised into Parquet, accumulated into a rolling 6-month corpus, visualised on a static GitHub Pages dashboard.

![CI](https://github.com/alex-wu/jobmarket_analyzer/actions/workflows/ci.yml/badge.svg)
![Pages](https://github.com/alex-wu/jobmarket_analyzer/actions/workflows/pages.yml/badge.svg)
![CodeQL](https://github.com/alex-wu/jobmarket_analyzer/actions/workflows/codeql.yml/badge.svg)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/alex-wu/jobmarket_analyzer/badge)](https://scorecard.dev/viewer/?uri=github.com/alex-wu/jobmarket_analyzer)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

**Status:** scope pivot in progress (2026-05-17, see [ADR-017](DECISIONS.md#adr-017--scope-cut-to-adzuna-only-post-v1-stabilisation)). Dashboard live at <https://alex-wu.github.io/jobmarket_analyzer/>. v1 ships **Adzuna-only**, multi-country (gb, de, fr, nl, es, it, pl) on a **weekly** Monday 06:00 UTC cron with `workflow_dispatch` for on-demand runs. Each preset produces a distinctly named `latest-{preset_id}.parquet` accumulated from the immutable dated archive ([ADR-019](DECISIONS.md#adr-019--multi-preset-latest-preset_id-release-naming), [ADR-020](DECISIONS.md#adr-020--accumulated-dataset-via-pure-function-recompute)). ATS adapters (Greenhouse / Lever / Ashby / Personio) and benchmark adapters (CSO / OECD / Eurostat) remain in the codebase, shelved by preset config until the multi-country unified merge proves stable end-to-end — see [ADR-017](DECISIONS.md#adr-017--scope-cut-to-adzuna-only-post-v1-stabilisation). Pipeline runs on Node 24 actions, Dependabot (weekly grouped npm + pip + actions), CodeQL (Python + JS), OpenSSF Scorecard, actionlint, and Dependabot auto-merge for patch+minor. Branch protection on `main` requires `test` + CodeQL checks. Day-to-day operations: [docs/operations.md](docs/operations.md). CI/CD reference: [docs/ci-cd-practices.md](docs/ci-cd-practices.md). Architecture: [DECISIONS.md](DECISIONS.md) + [docs/architecture.md](docs/architecture.md).

**v1 preset:** `data_analyst_eu` — data-analyst roles across 7 EU countries. The pipeline is preset-driven — `config/runs/*.yaml` declare what gets ingested. Adding a new role/geography is a YAML file plus one entry in the dashboard's presets manifest. Multiple presets run in parallel via GitHub Actions matrix; each produces its own `latest-{preset_id}.parquet`.

---

## What it does

1. **Ingest** — One Adzuna source adapter fetches across 7 EU countries (gb, de, fr, nl, es, it, pl) at ~105 API calls/week (42 % of free-tier quota). See [ADR-017](DECISIONS.md#adr-017--scope-cut-to-adzuna-only-post-v1-stabilisation) for why the active source set is Adzuna-only, [ADR-018](DECISIONS.md#adr-018--weekly-cadence--multi-country-single-run) for cadence rationale.
2. **Normalise** — Currency to EUR via ECB reference rates, salary period to annual, fuzzy-match titles to ISCO-08 occupation codes via ESCO, deduplicate by `posting_id`.
3. **Archive** — Each weekly run writes an immutable `data-{preset_id}-YYYY-MM-DD.parquet` to its own dated GitHub Release. Never modified, never deleted ([ADR-020](DECISIONS.md#adr-020--accumulated-dataset-via-pure-function-recompute)).
4. **Accumulate** — Publish step unions the last 180 days of dated releases for the preset, dedupes by `posting_id`, derives `first_seen_at` / `last_seen_at`, re-clobbers `latest-{preset_id}` Release with the unified parquet. Pure function — `latest` is recomputable from the archive at any time.
5. **Visualise** — Observable Framework dashboard on GitHub Pages reads `latest-{preset_id}.parquet` for the active preset (preset switcher in the UI). Every posting links back to its source URL.

---

## Quick start

Prerequisites: [uv](https://docs.astral.sh/uv/), Python 3.12 (uv will install), Node 24+ (for the dashboard site).

```bash
git clone https://github.com/alex-wu/jobmarket_analyzer.git
cd jobmarket_analyzer
uv sync
cp .env.example .env   # then fill in ADZUNA_APP_ID / ADZUNA_APP_KEY

# Sanity-check the preset before any HTTP calls (recommended for forks)
uv run jobpipe validate --preset config/runs/data_analyst_eu.yaml

# Run the v1 preset end-to-end against the live API
uv run jobpipe fetch --preset config/runs/data_analyst_eu.yaml --verbose
uv run jobpipe normalise --preset config/runs/data_analyst_eu.yaml
uv run jobpipe publish --preset config/runs/data_analyst_eu.yaml
uv run jobpipe gate --manifest data/publish/<run_id>/manifest.json --preset config/runs/data_analyst_eu.yaml

# Or skip live fetching and download the production sample from the latest release:
gh release download latest-data_analyst_eu -p "latest-data_analyst_eu.parquet" -p "manifest.json" \
  -R alex-wu/jobmarket_analyzer -D data/gh_databuild_samples/ --clobber

# Build the dashboard against the local Parquet sample
cd site && npm install && npm run dev   # http://127.0.0.1:3000
```

Live demo: <https://alex-wu.github.io/jobmarket_analyzer/>

For the day-to-day local-dev / refresh / push loops, see [docs/operations.md](docs/operations.md).

---

## Architecture (one-liner)

GitHub Actions weekly cron + matrix over presets → Python pipeline (`uv` env) → archive (dated Releases) → accumulate (pure-function union of last 180 days) → `latest-{preset_id}` Release as CDN → Observable Framework site with preset switcher (DuckDB-WASM) → GitHub Pages.

Full dataflow diagram: [docs/architecture.md](docs/architecture.md). Architectural decisions: [DECISIONS.md](DECISIONS.md).

---

## Extending

- **New preset (role / geography)** — copy `config/runs/data_analyst_eu.yaml`, change `preset_id`, `keywords`, `countries`. Add it to the workflow matrix and to the dashboard's presets manifest. No code change.
- **New source adapter** — out of scope for v1 per [ADR-017](DECISIONS.md#adr-017--scope-cut-to-adzuna-only-post-v1-stabilisation). The pluggable adapter pattern ([ADR-008](DECISIONS.md#adr-008--pluggable-adapter-pattern-sources--benchmarks)) survives — see [docs/adding-a-source.md](docs/adding-a-source.md) for the post-v1 pattern. Reactivation criteria documented in ADR-017.
- **New benchmark adapter** — same status. See [docs/adding-a-benchmark.md](docs/adding-a-benchmark.md) and ADR-017.

---

## Deploy

The dashboard lives at <https://alex-wu.github.io/jobmarket_analyzer/>. Two workflows back it:

- `.github/workflows/refresh.yml` — weekly Monday 06:00 UTC cron + manual dispatch, matrix over presets in `config/runs/*.yaml`. Runs the pipeline, uploads accumulated `latest-{preset_id}.parquet` + `manifest.json` to `latest-{preset_id}` + dated `data-{preset_id}-YYYY-MM-DD` GitHub Releases.
- `.github/workflows/pages.yml` — builds `site/` with Observable Framework, smoke-tests it, deploys via `actions/deploy-pages`. Triggers on push to `main` under `site/**`, on `refresh.yml` completion (via `workflow_run`), or via manual `workflow_dispatch`.

One-time manual GitHub setup (secrets, Pages source, workflow permissions, secret scanning) is checklisted in [docs/github-setup.md](docs/github-setup.md). Architectural rationale: [ADR-004](DECISIONS.md#adr-004--storage--delivery-parquet-via-github-releases-as-cdn), [ADR-016](DECISIONS.md#adr-016--github-pages-deploy-via-actionsdeploy-pages-from-the-monorepo), [ADR-019](DECISIONS.md#adr-019--multi-preset-latest-preset_id-release-naming).

---

## Open questions

What we know we haven't solved yet (preset switcher persistence, first-run backfill window, gate baseline after pivot, …) lives in [docs/open-questions.md](docs/open-questions.md).

---

## Project status

Phase-gated build per [DECISIONS.md](DECISIONS.md):

- [x] **P0** — scaffolding, git init, CI green
- [x] **P1** — Adzuna source adapter + raw Parquet
- [x] **P2** — normalisation + dedupe + strict schema
- [x] **P3** — ATS source adapters (Greenhouse, Lever, Ashby, Personio). **Shelved 2026-05-17 per [ADR-017](DECISIONS.md#adr-017--scope-cut-to-adzuna-only-post-v1-stabilisation).** Code remains in tree, `enabled: false` in preset.
- [x] **P4** — benchmark adapters (CSO PxStat, OECD SDMX, Eurostat SES) + ESCO/ISCO tagging via rapidfuzz. **Benchmark adapters shelved 2026-05-17 per [ADR-017](DECISIONS.md#adr-017--scope-cut-to-adzuna-only-post-v1-stabilisation).** ESCO/ISCO tagging stays live. HN Algolia + LLM ISCO fallback descoped from v1 per [ADR-013](DECISIONS.md#adr-013--hn-algolia--llm-client-descoped-from-v1).
- [x] **P5** — GH Actions refresh + Release upload.
- [x] **P6** — Observable Framework dashboard.
- [x] **P7** — Pages deploy via `actions/deploy-pages`.
- [x] **P9** — CI/CD modernisation (shipped 2026-05-15).
- [x] **P10** — Gate command + warn-mode (shipped 2026-05-16). Zero-row ATS investigation **closed by descope** per [ADR-017](DECISIONS.md#adr-017--scope-cut-to-adzuna-only-post-v1-stabilisation).

### Queued

- [ ] **P13** — Scope-pivot implementation. New `data_analyst_eu.yaml` preset (Adzuna-only, 7 countries), `export_accumulated()` primitive in `duckdb_io.py`, `latest-{preset_id}` workflow renaming, matrix strategy + preset-scoped concurrency, dashboard preset switcher. Folds in P8 (build-time data loaders — accumulated parquet at 150-250 MB cannot ship via DuckDB-WASM cold-load). See ADR-017..020 + the next-session handover doc.
- [ ] **P11** — Portfolio polish + first tagged release. Second preset (e.g. `software_developer_eu`), README hero screenshot, CHANGELOG seed, `v0.1.0` tag. Depends on P13.
- [ ] **P12** — Schema expansion. `experience_level`, `work_arrangement`, `skills`, `remote` derivation per [docs/dashboard_data_gaps.md](docs/dashboard_data_gaps.md). The `remote` column already exists in `PostingSchema` but is unpopulated for Adzuna (no raw signal in upstream payload).

---

## License

Apache-2.0. See [LICENSE](LICENSE). Third-party attributions in [NOTICE.md](NOTICE.md).

Contributions welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).
