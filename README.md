# jobmarket_analyzer

> Modular, free-tier job-market intelligence pipeline. Daily ingest from public APIs, normalise into Parquet, overlay official salary benchmarks, visualise on a static GitHub Pages dashboard.

![CI](https://github.com/alex-wu/jobmarket_analyzer/actions/workflows/ci.yml/badge.svg)
![Pages](https://github.com/alex-wu/jobmarket_analyzer/actions/workflows/pages.yml/badge.svg)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

**Status:** P5 complete (cron + publish + first public push). `refresh.yml` runs daily @ 06:00 UTC, fetches from all 5 source adapters (Adzuna + 4 ATS), normalises with a 180-day recency floor, and publishes a single flat `postings.parquet` + `manifest.json` to a re-clobbered `latest` GitHub Release and an immutable `data-YYYY-MM-DD` release per UTC day. Verified end-to-end on `alex-wu/jobmarket_analyzer`. OECD adapter is built but disabled (Cloudflare bot-protection on `sdmx.oecd.org`, see [ADR-011](DECISIONS.md#adr-011--oecd-sdmx-adapter-ships-disabled-cloudflare-bot-protection)). HN Algolia + LLM client descoped from v1 ([ADR-013](DECISIONS.md#adr-013--hn-algolia--llm-client-descoped-from-v1)); ISCO live match rate sits at ~56 % (Run 5, n=504) — LLM-fallback re-scope is now a P6-blocking decision. P6 builds the Observable Framework dashboard locally against `data/gh_databuild_samples/` then wires `pages.yml` in P7. See [DECISIONS.md](DECISIONS.md) for architecture rationale and [docs/architecture.md](docs/architecture.md) for the dataflow diagram.

**v1 preset:** data-analyst roles, Ireland-focused with Eurozone context. The pipeline is preset-driven — `config/runs/*.yaml` declare what gets ingested. Adding a new role/geography is a YAML file, not a code change.

---

## What it does

1. **Ingest** — Pluggable source adapters fetch postings from public APIs: Adzuna (Eurozone) and Greenhouse / Lever / Ashby / Personio (public boards for Dublin tech). Remotive is excluded — see [ADR-009](DECISIONS.md#adr-009--remotive-excluded-from-ingest-sources). HN Algolia + LLM-assisted extraction are descoped from v1 — see [ADR-013](DECISIONS.md#adr-013--hn-algolia--llm-client-descoped-from-v1).
2. **Normalise** — Currency to EUR via ECB reference rates, salary period to annual, fuzzy-match titles to ISCO-08 occupation codes via ESCO, deduplicate by URL + title + company.
3. **Benchmark** — Pluggable benchmark adapters pull official wage statistics (CSO PxStat for Ireland, OECD SDMX, Eurostat).
4. **Publish** — Partitioned Parquet bundle uploaded to a GitHub Release as a free CDN. Manifest records provenance.
5. **Visualise** — Observable Framework dashboard on GitHub Pages reads the Parquet directly via DuckDB-WASM. Every posting links back to its source URL.

---

## Quick start

Prerequisites: [uv](https://docs.astral.sh/uv/), Python 3.12 (uv will install), Node 20+ (for the dashboard site).

```bash
git clone https://github.com/alex-wu/jobmarket_analyzer.git
cd jobmarket_analyzer
uv sync
cp .env.example .env   # then fill in ADZUNA_APP_ID / ADZUNA_APP_KEY (optional — ATS adapters work credential-free)

# Run the v1 preset end-to-end against the live APIs (Adzuna is skipped if creds are absent)
uv run jobpipe fetch --preset config/runs/data_analyst_ireland.yaml --verbose
uv run jobpipe normalise --preset config/runs/data_analyst_ireland.yaml
uv run jobpipe publish --preset config/runs/data_analyst_ireland.yaml

# Or skip live fetching and download the production sample from the latest release:
gh release download latest -p "postings__postings.parquet" -p "manifest.json" \
  -R alex-wu/jobmarket_analyzer -D data/gh_databuild_samples/ --clobber

# Build the dashboard against the local Parquet sample (P6 — in progress)
cd site && npm ci && npx framework dev
```

Live demo: `https://alex-wu.github.io/jobmarket_analyzer/` (post-P7).

---

## Architecture (one-liner)

GitHub Actions cron → Python pipeline (`uv` env) → Parquet → GitHub Releases as CDN → Observable Framework site (DuckDB-WASM) → GitHub Pages.

Full dataflow diagram: [docs/architecture.md](docs/architecture.md). Architectural decisions: [DECISIONS.md](DECISIONS.md).

---

## Extending

- **New source** (e.g. another ATS provider, a new job board API): add one file under `src/jobpipe/sources/`. See [docs/adding-a-source.md](docs/adding-a-source.md).
- **New benchmark** (e.g. another national statistics agency): add one file under `src/jobpipe/benchmarks/`. See [docs/adding-a-benchmark.md](docs/adding-a-benchmark.md).
- **New role / geography**: add a YAML under `config/runs/`. No code change.

---

## Deploy

The dashboard lives at `https://<owner>.github.io/jobmarket_analyzer/` once P7 ships. Two workflows back it:

- `.github/workflows/refresh.yml` (P5) — cron + manual dispatch, runs the pipeline, uploads partitioned Parquet to `latest` + dated GitHub Releases.
- `.github/workflows/pages.yml` (P7) — builds `site/` with Observable Framework, deploys via `actions/deploy-pages`.

One-time manual GitHub setup (secrets, Pages source, workflow permissions, secret scanning) is checklisted in [docs/github-setup.md](docs/github-setup.md). Architectural rationale: [ADR-004](DECISIONS.md#adr-004--storage--delivery-parquet-via-github-releases-as-cdn), [ADR-016](DECISIONS.md#adr-016--github-pages-deploy-via-actionsdeploy-pages-from-the-monorepo).

---

## Open questions

What we know we haven't solved yet (OECD unblock, dashboard recency, ISCO live-match-rate, ...) lives in [docs/open-questions.md](docs/open-questions.md).

---

## Project status

Phase-gated build per [DECISIONS.md](DECISIONS.md):

- [x] **P0** — scaffolding, git init, CI green
- [x] **P1** — Adzuna source adapter + raw Parquet
- [x] **P2** — normalisation + dedupe + strict schema
- [x] **P3** — ATS source adapters (Greenhouse, Lever, Ashby, Personio). Remotive excluded ([ADR-009](DECISIONS.md#adr-009--remotive-excluded-from-ingest-sources)).
- [x] **P4** — benchmark adapters (CSO PxStat, OECD SDMX, Eurostat SES) + ESCO/ISCO tagging via rapidfuzz. OECD ships disabled ([ADR-011](DECISIONS.md#adr-011--oecd-sdmx-adapter-ships-disabled-cloudflare-bot-protection)); HN Algolia + LLM ISCO fallback descoped from v1 ([ADR-013](DECISIONS.md#adr-013--hn-algolia--llm-client-descoped-from-v1)).
- [x] **P5** — GH Actions refresh + Release upload. Daily 06:00 UTC cron + workflow dispatch. `publish.partition_by: []` writes a single flat `postings.parquet` (hive layout strips columns on flatten — see session log). Recency floor at 180 days (Adzuna `max_days_old` + `normalise.since_days`). Verified Run 5 on 2026-05-15.
- [ ] **P6** — Observable Framework site + GH Pages. Builds locally against `data/gh_databuild_samples/postings__postings.parquet`.
- [ ] **P7** — polish, second preset, screenshots, `pages.yml`

---

## License

Apache-2.0. See [LICENSE](LICENSE). Third-party attributions in [NOTICE.md](NOTICE.md).

Contributions welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).
