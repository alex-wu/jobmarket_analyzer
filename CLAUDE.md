# CLAUDE.md

Guidance for Claude Code (claude.ai/code) sessions in this repo. Read first.

## Status

Active phased build. v1 = data-analyst roles, Ireland/Eurozone, GitHub Pages dashboard. Phase plan and acceptance criteria in [README.md](README.md) and [DECISIONS.md](DECISIONS.md). Current phase target: see the unchecked boxes in the README phase plan.

**Authoritative docs (in priority order):**
1. **The newest log in [docs/sessions/](docs/sessions/)** — start here. Captures what landed last session, issues hit, and the next-session handover. Read [docs/sessions/README.md](docs/sessions/README.md) for the convention; **write a new log before ending your session**.
2. [DECISIONS.md](DECISIONS.md) — locked architectural choices and their WHY
3. [docs/architecture.md](docs/architecture.md) — dataflow diagram
4. [README.md](README.md) — quickstart + phase plan
5. The plan file at `~/.claude/plans/i-want-to-create-polymorphic-quokka.md` — the original implementation plan
6. [docs/history/](docs/history/) — superseded specs, kept for context

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

- `src/jobpipe/sources/` — one adapter per source TYPE (Adzuna, Greenhouse, Lever, Ashby, Personio; Remotive excluded per ADR-009; HN Algolia deferred to the LLM-client follow-up PR). Each registers itself via `@register("name")` and emits a DataFrame conforming to `PostingSchema`. **All HTTP and side effects live here.**
- `src/jobpipe/benchmarks/` — same pattern for benchmark series (CSO PxStat, Eurostat; OECD adapter implemented but disabled per ADR-011 — Cloudflare blocker). `_common.py` ships shared `last_fetch_mtime` / `should_skip` / `convert_benchmark_to_eur` helpers. Each adapter accepts an optional `rates` kwarg.
- `src/jobpipe/isco/` — pure ISCO-08 tagger. `loader.py` loads the static ESCO snapshot; `tagger.py` runs rapidfuzz `token_set_ratio` at cutoff 88. Slotted into `normalise.run` before dedupe; callers may inject a `labels_df` to keep purity.
- `src/jobpipe/normalise.py` — **pure functions**: DataFrames in, DataFrames out. No HTTP, no FS, no DB. FX conversion → P50 recompute → ISCO tagging → cross-source dedupe → strict-schema validation.
- `src/jobpipe/runner.py` — orchestrates a preset end-to-end. `fetch_sources` + `fetch_benchmarks` fan out fail-isolated per adapter. `run_normalise` writes sibling `postings.parquet` + `benchmarks.parquet`.
- `src/jobpipe/cli.py` — Typer entry point: `jobpipe fetch | normalise | publish`.
- `src/jobpipe/llm.py` — optional OpenAI-compatible client. **Stub as of P4** — contract defined (`classify_title_to_isco`, `LLMUnavailableError`) but calls raise. Real client lands in the HN-Algolia follow-up.
- `config/runs/` — YAML presets declare WHAT to fetch. Adding a new role/geo = new YAML, no code change. Per-adapter `min_interval_hours` throttles re-fetch.
- `config/companies/` — shared ATS slug lists referenced by presets.
- `config/esco/isco08_labels.parquet` — static ESCO label snapshot (2 137 rows × 436 ISCO codes). Rebuild via `scripts/build_esco_snapshot.py`. See `config/esco/README.md` for provenance + EUPL-1.2 attribution.
- `site/` — Observable Framework project (lands in P6). Data loader fetches the `latest` GitHub Release.
- `tests/fixtures/<area>/<adapter>/` — hand-built JSON responses (one trimmed real sample per adapter). The repo abandoned `pytest-recording` VCR after P3; tests use `httpx.MockTransport` + these fixtures instead.

## Hard rules

**Library leverage first** — Don't write what an active FOSS library already does (HTTP retries → `tenacity`; schema validation → `pandera`; fuzzy match → `rapidfuzz`; FX rates → ECB CSV; YAML parsing → `pyyaml`; config validation → `pydantic`; CLI → `typer`). A new top-level dep needs a one-line justification in the PR description.

**Hard exclusions** (enforced by `tests/test_license_audit.py`):
- `dlthub` — proprietary; only `dlt` permitted (and we don't even use that in v1).
- `dagster-cloud` — paid hosting; we run on GH Actions, not Dagster.
- Any paid scraping/proxy service.

**Module purity:**
- `src/jobpipe/normalise.py` and `src/jobpipe/isco/` must be pure. DataFrames in, DataFrames out. Inject FS-loaded data (rates, labels) as parameters with sensible defaults.
- All side effects (HTTP, FS, DB) live in `sources/`, `benchmarks/`, `runner.py`, and `duckdb_io.py`.

**Source adapters fail-isolated:** one source's HTTP error does not abort the run; downstream consumes what succeeded. But a run with 0 postings across all enabled sources MUST exit non-zero (not silently produce an empty dashboard).

**Re-runs idempotent:** dedupe by sha1 of normalised URL (or `title+company+country` when URL absent). Re-running the same preset on the same day must not duplicate rows.

**LLM optional, always:** every transformation has a non-LLM fallback. Pipeline must materialise end-to-end with `LLM_ENABLED=false`.

**Secrets:** `.env` only (gitignored), surfaced via `pydantic-settings`. Catalogued in `.env.example`. Never read, echo, or commit `.env`.

## Testing discipline

- **Hand-built JSON fixtures under `tests/fixtures/<area>/<adapter>/`** drive `httpx.MockTransport`-based unit tests. P3 abandoned `pytest-recording` VCR after the noqa-shuffle problems; keep the new pattern.
- **Pre-flight every external endpoint** before writing a parser — probe the response shape with httpx + save a trimmed real sample as the fixture. Document any divergence (deprecated dataset codes, Cloudflare gating, etc.) in the session log before writing parser code.
- **LLM tests** use `pytest-httpserver` fake endpoint when the real client lands — never real LLM calls in CI.
- **Schema tests** — every adapter test must assert `PostingSchema.validate(output, lazy=True)` or `BenchmarkSchema.validate(...)` passes.
- **Coverage gates:** ≥80% line, ≥70% branch overall; per-adapter coverage ≥90% is the team norm (some benchmark adapters dipped into the mid-80s in P4 — pull them back up when fixtures grow).
- **Windows pytest flake:** an intermittent `numpy: cannot load module more than once per process` import error appears when running a *single* benchmark test file in isolation. Workaround: clear `__pycache__` and run the broader `tests/benchmarks/` selection (or the full suite). P3 + P4 session logs both flag this.

## Phase-gated build

One PR per phase. Each PR: code + tests + README/CHANGELOG delta. Do not skip ahead. Phases defined in [DECISIONS.md](DECISIONS.md) and the README plan checklist.

## Git workflow (project-level)

The global `~/.claude/CLAUDE.md` governs commit format, pre-snapshot rules, and pushed-protections. In addition for this repo:

- One feature branch per phase (`p1-adzuna-source`, `p2-normalise`, ...).
- PR against `main`. CI must pass. Squash-merge.
- Tag `v0.1.0` when all P0–P7 acceptance criteria pass simultaneously.

## Open questions / verify before P5+

- **Adzuna free tier**: resolved in P1 — `max_pages=5 × results_per_page=50 = 250` per fetch + `min_interval_hours=24` knob (see `docs/sessions/2026-05-11-p1-live-verification.md`).
- **Remotive ToS**: resolved in P3 — excluded entirely. ADR-009.
- **ESCO local API**: superseded — the live API's `/api/search` and `/api/resource/concept?isInScheme=...` paginations are broken past offset=100 as of v1.2.1. We walk the ISCO concept tree instead (ADR-010); static snapshot at `config/esco/isco08_labels.parquet` is the runtime source of truth.
- **OECD live access**: open, due before re-enabling — `sdmx.oecd.org` is Cloudflare-gated. Adapter ships disabled (ADR-011). Try authenticated API key, CSV mirror, or fixed-egress proxy before flipping `enabled: true`.
- **`--verbose` httpx credential leak**: open, **MUST FIX BEFORE P5** wires `.github/workflows/refresh.yml`. httpx INFO logs emit the full request URL including Adzuna `app_id`/`app_key`. Add a `logging.Filter` to `cli.py` or use `httpx.event_hooks` to rewrite logged URLs.
- **Adzuna posting recency**: open, decision due P6. Live P1 returned `posted_at` up to a year old. P6 dashboard work decides between filter / age column / freshness badge.
- **`salary_min_eur == 0` rows**: open, decision due P6. Adzuna emits a small non-zero count of zero-floored salaries; surface or hide.
- **CSO 4-digit ISCO coarseness**: open for the dashboard (P6) to surface. ADR-012 documents the umbrella-bucket mapping; dashboard should not present CSO bucket-1 numbers as if they were ISCO-2511-specific.
- **ISCO live match rate on real data**: open, needs a live `jobpipe normalise` against the 499-row P3 sample. Below 60% triggers the LLM-fallback PR priority bump.
