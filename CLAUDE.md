# CLAUDE.md

Guidance for Claude Code (claude.ai/code) sessions in this repo. Read first.

## Status

Active phased build. v1 = data-analyst roles, Ireland/Eurozone, GitHub Pages dashboard. Phase plan and acceptance criteria in [README.md](README.md) and [DECISIONS.md](DECISIONS.md). Current phase target: see the unchecked boxes in the README phase plan.

**Authoritative docs (in priority order):**
1. [DECISIONS.md](DECISIONS.md) — locked architectural choices and their WHY
2. [docs/architecture.md](docs/architecture.md) — dataflow diagram
3. [README.md](README.md) — quickstart + phase plan
4. The plan file at `~/.claude/plans/i-want-to-create-polymorphic-quokka.md` — the original implementation plan
5. [docs/history/](docs/history/) — superseded specs, kept for context

When this file conflicts with the user's global `~/.claude/CLAUDE.md`, the global wins for style/git/safety; this file wins for project-specific architecture and conventions.

## Commands

```bash
# Env
uv sync                                    # install / sync deps from uv.lock
uv run pre-commit install                  # one-time

# Pipeline (end-to-end)
uv run jobpipe fetch     --preset config/runs/data_analyst_ireland.yaml
uv run jobpipe normalise --preset config/runs/data_analyst_ireland.yaml
uv run jobpipe publish   --preset config/runs/data_analyst_ireland.yaml

# Quality gates (also enforced by CI)
uv run ruff check
uv run ruff format --check
uv run mypy --strict src/jobpipe
uv run pytest --cov=jobpipe --cov-fail-under=80

# Dashboard (Observable Framework)
cd site && npm ci && npx framework dev     # local preview
cd site && npx framework build             # static build (CI does this)
```

## Architecture (one-liner)

GitHub Actions cron → Python pipeline (`uv` env) → DuckDB + partitioned Parquet → GitHub Releases as CDN → Observable Framework site (DuckDB-WASM in browser) → GitHub Pages.

Full diagram in [docs/architecture.md](docs/architecture.md).

## Module layout

- `src/jobpipe/sources/` — one adapter per source TYPE (Adzuna, Greenhouse, Lever, Ashby, Personio, Remotive, HN Algolia). Each registers itself via `@register("name")` and emits a DataFrame conforming to `PostingSchema`. **All HTTP and side effects live here.**
- `src/jobpipe/benchmarks/` — same pattern for benchmark series (CSO PxStat, OECD SDMX, Eurostat). Emits `BenchmarkSchema`.
- `src/jobpipe/normalise.py` — **pure functions**: DataFrames in, DataFrames out. No HTTP, no FS, no DB. FX conversion, period normalisation, dedupe, ISCO tagging.
- `src/jobpipe/runner.py` — orchestrates a preset end-to-end. Fan-out is fail-isolated per adapter.
- `src/jobpipe/cli.py` — Typer entry point: `jobpipe fetch | normalise | publish`.
- `src/jobpipe/llm.py` — optional OpenAI-compatible client. Only invoked when `LLM_ENABLED=true`.
- `config/runs/` — YAML presets declare WHAT to fetch. Adding a new role/geo = new YAML, no code change.
- `config/companies/` — shared ATS slug lists referenced by presets.
- `site/` — Observable Framework project. Data loader fetches the `latest` GitHub Release.
- `tests/cassettes/` — pytest-recording VCR fixtures. Never live HTTP in CI.

## Hard rules

**Library leverage first** — Don't write what an active FOSS library already does (HTTP retries → `tenacity`; schema validation → `pandera`; fuzzy match → `rapidfuzz`; FX rates → ECB CSV; YAML parsing → `pyyaml`; config validation → `pydantic`; CLI → `typer`). A new top-level dep needs a one-line justification in the PR description.

**Hard exclusions** (enforced by `tests/test_license_audit.py`):
- `dlthub` — proprietary; only `dlt` permitted (and we don't even use that in v1).
- `dagster-cloud` — paid hosting; we run on GH Actions, not Dagster.
- Any paid scraping/proxy service.

**Module purity:**
- `defs/enrich/*` and `normalise.py` must be pure. DataFrames in, DataFrames out.
- All side effects (HTTP, FS, DB) live in `sources/`, `benchmarks/`, and `duckdb_io.py`.

**Source adapters fail-isolated:** one source's HTTP error does not abort the run; downstream consumes what succeeded. But a run with 0 postings across all enabled sources MUST exit non-zero (not silently produce an empty dashboard).

**Re-runs idempotent:** dedupe by sha1 of normalised URL (or `title+company+country` when URL absent). Re-running the same preset on the same day must not duplicate rows.

**LLM optional, always:** every transformation has a non-LLM fallback. Pipeline must materialise end-to-end with `LLM_ENABLED=false`.

**Secrets:** `.env` only (gitignored), surfaced via `pydantic-settings`. Catalogued in `.env.example`. Never read, echo, or commit `.env`.

## Testing discipline

- **VCR cassettes** (`pytest-recording`) recorded BEFORE writing a parser. Test against the fixture, never live HTTP in CI.
- **LLM tests** use `pytest-httpserver` fake endpoint — never real LLM calls.
- **Schema tests** — every adapter test must assert `PostingSchema.validate(output, lazy=True)` passes.
- **Integration test** at `tests/integration/test_pipeline.py` exercises 3 fixture sources → normalise → publish manifest.
- **Coverage gates:** ≥80% line, ≥70% branch.

## Phase-gated build

One PR per phase. Each PR: code + tests + README/CHANGELOG delta. Do not skip ahead. Phases defined in [DECISIONS.md](DECISIONS.md) and the README plan checklist.

## Git workflow (project-level)

The global `~/.claude/CLAUDE.md` governs commit format, pre-snapshot rules, and pushed-protections. In addition for this repo:

- One feature branch per phase (`p1-adzuna-source`, `p2-normalise`, ...).
- PR against `main`. CI must pass. Squash-merge.
- Tag `v0.1.0` when all P0–P7 acceptance criteria pass simultaneously.

## Open questions / verify before P1

- Adzuna free tier: 250 calls/MONTH or /day? Affects `refresh.yml` cron cadence.
- Remotive ToS as of P3 — confirm attribution-in-footer satisfies their "no redistribution as competing board" clause.
- ESCO local API replacement — pin to the static `config/esco/isco08_labels.parquet` snapshot until the new API ships.
