# Contributing

Thanks for considering a contribution. This project aims to stay small, modular, and free to run.

## Ground rules

- **Leverage active FOSS first.** Don't write custom code when a maintained library covers the use case. New top-level dependencies need a one-line justification in the PR.
- **Pluggable, not coupled.** New sources and benchmarks are new files under `src/jobpipe/sources/` and `src/jobpipe/benchmarks/`. The rest of the pipeline must not change.
- **No paid SaaS.** The pipeline must remain runnable on the free tiers of the services it touches. Hard exclusions: `dlthub` (proprietary), `dagster-cloud` (paid hosting), any paid scraping/proxy service.
- **LLM is optional, always.** Every transformation has a deterministic fallback. The pipeline must materialise end-to-end with `LLM_ENABLED=false`.
- **License audit.** `tests/test_license_audit.py` rejects PRs that introduce excluded packages.

## Dev setup

```bash
uv sync
uv run pre-commit install
cp .env.example .env   # only ADZUNA_* needed for source-adapter dev
```

## Quality gates (also enforced by CI)

```bash
uv run ruff check
uv run ruff format --check
uv run mypy --strict src/jobpipe
uv run pytest --cov=jobpipe --cov-fail-under=80
```

## Adding a new source adapter

Walkthrough: [docs/adding-a-source.md](docs/adding-a-source.md). Summary:

1. Create `src/jobpipe/sources/<name>.py` implementing the `SourceAdapter` Protocol and decorated with `@register("<name>")`.
2. Output a `pd.DataFrame` conforming to `PostingSchema` (`src/jobpipe/schemas.py`).
3. Add a VCR cassette under `tests/cassettes/<name>/` and unit tests under `tests/sources/test_<name>.py`.
4. Wire the adapter into a preset YAML (set `enabled: true`).

## Adding a new benchmark adapter

Walkthrough: [docs/adding-a-benchmark.md](docs/adding-a-benchmark.md). Same pattern under `src/jobpipe/benchmarks/`.

## Adding a new preset

Add a YAML under `config/runs/`. No code change. The CI matrix in `refresh.yml` picks it up automatically.

## Commit + PR conventions

- Conventional prefix: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`, `ci:`, `perf:`, `style:`.
- One PR per phase (see README phase plan).
- Each PR: code + tests + README/CHANGELOG delta where relevant.
- CI must pass. No `--no-verify`.
- No `git push --force` to `main`.

## Reporting an issue

Open an issue with:
- What preset you ran
- Output of `uv run jobpipe --version`
- The first stack trace / log line that broke
- Whether `LLM_ENABLED` was true or false
