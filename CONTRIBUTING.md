# Contributing

Thanks for considering a contribution. This project aims to stay small, modular, and free to run. Read this file end-to-end before opening a PR.

## Authoritative docs (in priority order)

1. [DECISIONS.md](DECISIONS.md) — locked architectural choices and their WHY (ADR-lite).
2. [docs/architecture.md](docs/architecture.md) — dataflow diagram + module layout.
3. [README.md](README.md) — quickstart + phase plan.
4. [docs/open-questions.md](docs/open-questions.md) — what we know we haven't solved yet.
5. [CHANGELOG.md](CHANGELOG.md) — phase-by-phase release notes.

If you change architecture, update ADRs (and `docs/architecture.md`). If you change scope, update the README phase plan and `docs/open-questions.md`.

## Dev setup

```bash
uv sync
uv run pre-commit install
cp .env.example .env   # only ADZUNA_* needed for source-adapter dev
```

Tooling is managed via [`uv`](https://docs.astral.sh/uv/) for Python and `npm` for the dashboard site (Node 24+). CI runs the same commands. Don't introduce per-language version managers (`pyenv`, `nvm`, etc.).

## Quality gates (also enforced by CI)

```bash
uv run ruff check
uv run ruff format --check
uv run mypy --strict src/jobpipe
uv run pytest --cov=jobpipe --cov-fail-under=80
```

## Hard rules

**Library leverage first.** Don't write what an active FOSS library already does:
- HTTP retries → `tenacity`
- Schema validation → `pandera`
- Fuzzy match → `rapidfuzz`
- FX rates → ECB CSV
- YAML parsing → `pyyaml`
- Config validation → `pydantic`
- CLI → `typer`

A new top-level dep needs a one-line justification in the PR description.

**Hard exclusions** (enforced by `tests/test_license_audit.py`):
- `dlthub` — proprietary; only `dlt` permitted (and we don't even use that in v1).
- `dagster-cloud` — paid hosting; we run on GH Actions, not Dagster.
- Any paid scraping / proxy service.

**Pluggable, not coupled.** New sources and benchmarks are new files under `src/jobpipe/sources/` and `src/jobpipe/benchmarks/`. The rest of the pipeline must not change.

**Module purity.**
- `src/jobpipe/normalise.py` and `src/jobpipe/isco/` must be pure. DataFrames in, DataFrames out. Inject FS-loaded data (rates, ISCO labels) as parameters with sensible defaults.
- All side effects (HTTP, FS, DB) live in `src/jobpipe/sources/`, `src/jobpipe/benchmarks/`, `src/jobpipe/runner.py`, and `src/jobpipe/duckdb_io.py`.

**Source adapters fail-isolated.** One source's HTTP error does not abort the run; downstream consumes what succeeded. But a run with **zero** postings across all enabled sources MUST exit non-zero (loud failure, not a silent empty dashboard).

**Re-runs idempotent.** Dedupe by sha1 of normalised URL (or `title+company+country` when URL absent). Re-running the same preset on the same day must not duplicate rows.

**LLM optional, always.** Every transformation has a non-LLM fallback. The pipeline must materialise end-to-end with `LLM_ENABLED=false`. v1 keeps the LLM client as a stub — see [ADR-013](DECISIONS.md#adr-013--hn-algolia--llm-client-descoped-from-v1).

**Secrets.** `.env` only (gitignored), surfaced via `pydantic-settings`. Catalogued in `.env.example`. Never read, echo, or commit `.env`. URL credential leaks are scrubbed centrally — see [ADR-015](DECISIONS.md#adr-015--httpx-credential-redaction-filter-on-the-cli-logger).

## Testing discipline

- **Hand-built JSON fixtures under `tests/fixtures/<area>/<adapter>/`** drive `httpx.MockTransport`-based unit tests (preferred over VCR-cassette recording).
- **Pre-flight every external endpoint** before writing a parser — probe the response shape with `httpx` + save a trimmed real sample as the fixture. Document any divergence (deprecated dataset codes, Cloudflare gating, etc.) in the PR description.
- **Schema tests** — every adapter test must assert `PostingSchema.validate(output, lazy=True)` or `BenchmarkSchema.validate(...)` passes.
- **Coverage gates:** ≥80% line, ≥70% branch overall; per-adapter coverage ≥90% is the norm.

**Windows pytest flake:** an intermittent `numpy: cannot load module more than once per process` import error appears when running a *single* benchmark test file in isolation. Workaround: clear `__pycache__` and run the broader `tests/benchmarks/` selection (or the full suite).

## Scoped PRs

One PR per coherent change. Each PR: code + tests + README/CHANGELOG delta where relevant.

## Git workflow

- One feature branch per change (`feat/<short-name>`).
- PR against `main`. CI must pass. No `--no-verify`.
- Squash-merge.
- Conventional commit prefixes: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`, `ci:`, `perf:`, `style:`.
- No `git push --force` to `main`.

## Adding things

- **New preset (role / geography)** — copy `config/runs/data_analyst_eu.yaml`, change `preset_id`, `keywords`, `countries`. Add `preset_id` to `strategy.matrix.preset` in `.github/workflows/refresh.yml`, and un-hardcode `PRESET_ID` in `.github/workflows/pages.yml` and `site/src/data/postings.parquet.js` (both currently pin `data_analyst_eu`). Multi-preset auto-discovery is queued per [ADR-019](DECISIONS.md#adr-019--multi-preset-latest-preset_id-release-naming); until it lands this is the honest procedure.
- **New source adapter** — **post-v1 only** per [ADR-017](DECISIONS.md#adr-017--scope-cut-to-adzuna-only-post-v1-stabilisation). The pluggable pattern survives; walkthrough at [docs/adding-a-source.md](docs/adding-a-source.md) is the reactivation path.
- **New benchmark adapter** — **post-v1 only** per [ADR-017](DECISIONS.md#adr-017--scope-cut-to-adzuna-only-post-v1-stabilisation). Follows the same Protocol pattern as sources, under `src/jobpipe/benchmarks/` (see the note in [docs/adding-a-source.md](docs/adding-a-source.md)).
- **New role / geography**: add a YAML under `config/runs/` (plus the workflow/loader touch-points above).

## Reporting an issue

Open an issue with:
- What preset you ran
- Output of `uv run jobpipe --version`
- The first stack trace / log line that broke
- Whether `LLM_ENABLED` was true or false (it should be `false` in v1; if true, that's the issue)

## Licence

Apache-2.0. See [LICENSE](LICENSE). Third-party attributions in [NOTICE.md](NOTICE.md). By contributing, you agree your contributions are licensed under the same terms.
