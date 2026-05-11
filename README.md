# jobmarket_analyzer

> Modular, free-tier job-market intelligence pipeline. Daily ingest from public APIs, normalise into Parquet, overlay official salary benchmarks, visualise on a static GitHub Pages dashboard.

![CI](https://github.com/USER/jobmarket_analyzer/actions/workflows/ci.yml/badge.svg)
![Pages](https://github.com/USER/jobmarket_analyzer/actions/workflows/pages.yml/badge.svg)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

**Status:** P0 scaffolding (pre-MVP). See [DECISIONS.md](DECISIONS.md) for architecture rationale and [docs/architecture.md](docs/architecture.md) for the dataflow diagram.

**v1 preset:** data-analyst roles, Ireland-focused with Eurozone context. The pipeline is preset-driven — `config/runs/*.yaml` declare what gets ingested. Adding a new role/geography is a YAML file, not a code change.

---

## What it does

1. **Ingest** — Pluggable source adapters fetch postings from public APIs: Adzuna (Eurozone), Greenhouse / Lever / Ashby / Personio (public boards for Dublin tech), Remotive (EU filter), Hacker News Algolia.
2. **Normalise** — Currency to EUR via ECB reference rates, salary period to annual, fuzzy-match titles to ISCO-08 occupation codes via ESCO, deduplicate by URL + title + company.
3. **Benchmark** — Pluggable benchmark adapters pull official wage statistics (CSO PxStat for Ireland, OECD SDMX, Eurostat).
4. **Publish** — Partitioned Parquet bundle uploaded to a GitHub Release as a free CDN. Manifest records provenance.
5. **Visualise** — Observable Framework dashboard on GitHub Pages reads the Parquet directly via DuckDB-WASM. Every posting links back to its source URL.

---

## Quick start

Prerequisites: [uv](https://docs.astral.sh/uv/), Python 3.12 (uv will install), Node 20+ (for the dashboard site).

```bash
git clone https://github.com/USER/jobmarket_analyzer.git
cd jobmarket_analyzer
uv sync
cp .env.example .env   # then fill in ADZUNA_APP_ID and ADZUNA_APP_KEY

# Run the v1 preset end-to-end against recorded HTTP fixtures
uv run jobpipe fetch --preset config/runs/data_analyst_ireland.yaml --use-cassettes
uv run jobpipe normalise --preset config/runs/data_analyst_ireland.yaml
uv run jobpipe publish --preset config/runs/data_analyst_ireland.yaml

# Build the dashboard against the local Parquet bundle
cd site && npm ci && npx framework dev
```

Live demo: `https://USER.github.io/jobmarket_analyzer/` (post-P6).

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

## Project status

Phase-gated build per [DECISIONS.md](DECISIONS.md):

- [x] **P0** — scaffolding, git init, CI green
- [x] **P1** — Adzuna source adapter + raw Parquet
- [ ] **P2** — normalisation + dedupe + strict schema
- [ ] **P3** — ATS + community source adapters
- [ ] **P4** — benchmark adapters + ESCO/ISCO tagging
- [ ] **P5** — GH Actions refresh + Release upload
- [ ] **P6** — Observable Framework site + GH Pages
- [ ] **P7** — polish, second preset, screenshots

---

## License

Apache-2.0. See [LICENSE](LICENSE). Third-party attributions in [NOTICE.md](NOTICE.md).

Contributions welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).
