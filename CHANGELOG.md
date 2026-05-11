# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
