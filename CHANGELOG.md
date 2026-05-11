# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed — P1 (2026-05-11)
- `AdzunaAdapter.fetch()` now collapses within-source duplicate `posting_id`s before returning. A single Adzuna posting can match multiple keywords ("data analyst" + "analytics engineer"), which previously broke `PostingSchema`'s uniqueness check during live runs. Cross-source dedupe remains P2 work.

### Added — P1 (2026-05-11)
- `AdzunaAdapter` (`src/jobpipe/sources/adzuna.py`): paginated fetch against `api.adzuna.com/v1/api/jobs/{country}/search/{page}`, normalises each result to a `PostingSchema` row, fail-isolates HTTP errors via `SourceFetchError`, retries transient failures via `tenacity`.
- `AdzunaConfig` extends `SourceConfig` with `results_per_page`, `max_pages`, `timeout_seconds`, `min_interval_hours`.
- Preset loader + runner (`src/jobpipe/runner.py`): `load_preset()` parses + validates run YAMLs (`PresetError` on malformed input), `fetch_sources()` fans out to enabled adapters with fail-isolation, `write_raw_parquet()` writes `data/raw/<preset_id>__<run_id>/postings_raw.parquet`. Zero rows across all enabled sources raises `EmptyRunError`.
- CLI `jobpipe fetch` wired to runner; `--verbose` flag for INFO logging; explicit exit code 2 on `PresetError` / `EmptyRunError`.
- `data_analyst_ireland.yaml` preset: adzuna enabled with country `gb` (English-language labour-market proxy; Ireland not served by Adzuna in 2026 — documented inline).
- Adzuna adapter tests (`tests/sources/test_adzuna.py`): synthetic JSON fixtures + `httpx.MockTransport` cover happy path, missing salary, paging short-circuit, missing credentials, HTTP 5xx error, empty response, `max_results` cap, and self-registration on import.
- Runner tests (`tests/test_runner.py`): preset loader error paths, adapter fan-out, fail-isolation, end-to-end Parquet write.

### Added — P0 (2026-05-11)
- Initial project scaffolding: `pyproject.toml`, `uv.lock`, Apache-2.0 licence, README, CONTRIBUTING, DECISIONS, NOTICE.
- Pluggable `SourceAdapter` and `BenchmarkAdapter` Protocols + registry decorators (no concrete adapters yet).
- Pandera schema skeletons (`PostingSchema`, `BenchmarkSchema`).
- Typer CLI skeleton (`jobpipe fetch | normalise | publish`).
- pydantic-settings configuration.
- v1 preset YAML (`config/runs/data_analyst_ireland.yaml`) with all sources disabled until per-phase activation.
- CI workflow (`.github/workflows/ci.yml`): ruff, mypy strict, pytest with coverage gate, licence audit.
- Pre-commit hooks (ruff, mypy, end-of-file fixer, check-yaml/toml).
- Architecture diagram in `docs/architecture.md`.
- Original Dagster-centric spec archived under `docs/history/`.

[Unreleased]: https://github.com/USER/jobmarket_analyzer/compare/HEAD...HEAD
