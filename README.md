# jobmarket_analyzer

> Modular, free-tier job-market intelligence pipeline. Daily ingest from public APIs, normalise into Parquet, overlay official salary benchmarks, visualise on a static GitHub Pages dashboard.

![CI](https://github.com/USER/jobmarket_analyzer/actions/workflows/ci.yml/badge.svg)
![Pages](https://github.com/USER/jobmarket_analyzer/actions/workflows/pages.yml/badge.svg)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

**Status:** P4 complete (benchmarks + ISCO tagger) — 5 source adapters + ISCO-08 fuzzy tagger + CSO/Eurostat benchmark adapters writing a sibling `benchmarks.parquet` next to `postings.parquet`. OECD adapter is built but disabled in the preset (Cloudflare bot-protection on `sdmx.oecd.org`); HN Algolia and the dashboard land in follow-up PRs. See [DECISIONS.md](DECISIONS.md) for architecture rationale and [docs/architecture.md](docs/architecture.md) for the dataflow diagram.

**v1 preset:** data-analyst roles, Ireland-focused with Eurozone context. The pipeline is preset-driven — `config/runs/*.yaml` declare what gets ingested. Adding a new role/geography is a YAML file, not a code change.

---

## What it does

1. **Ingest** — Pluggable source adapters fetch postings from public APIs: Adzuna (Eurozone) and Greenhouse / Lever / Ashby / Personio (public boards for Dublin tech). Hacker News Algolia lands in P4 alongside LLM-assisted extraction. Remotive is excluded — see [ADR-009](DECISIONS.md#adr-009--remotive-excluded-from-ingest-sources).
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
cp .env.example .env   # then fill in ADZUNA_APP_ID / ADZUNA_APP_KEY (optional — ATS adapters work credential-free)

# Run the v1 preset end-to-end against the live APIs (Adzuna is skipped if creds are absent)
uv run jobpipe fetch --preset config/runs/data_analyst_ireland.yaml --verbose
uv run jobpipe normalise --preset config/runs/data_analyst_ireland.yaml
uv run jobpipe publish --preset config/runs/data_analyst_ireland.yaml    # P5 wires Release upload

# Build the dashboard against the local Parquet bundle (P6)
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
- [x] **P2** — normalisation + dedupe + strict schema
- [x] **P3** — ATS source adapters (Greenhouse, Lever, Ashby, Personio). Remotive excluded ([ADR-009](DECISIONS.md#adr-009--remotive-excluded-from-ingest-sources)); HN Algolia deferred to P4.
- [x] **P4** — benchmark adapters (CSO PxStat, OECD SDMX, Eurostat SES) + ESCO/ISCO tagging via rapidfuzz. OECD ships disabled (Cloudflare-blocked on `sdmx.oecd.org`); HN Algolia + LLM ISCO fallback split into a follow-up PR.
- [ ] **P5** — GH Actions refresh + Release upload
- [ ] **P6** — Observable Framework site + GH Pages
- [ ] **P7** — polish, second preset, screenshots

---

## License

Apache-2.0. See [LICENSE](LICENSE). Third-party attributions in [NOTICE.md](NOTICE.md).

Contributions welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).
