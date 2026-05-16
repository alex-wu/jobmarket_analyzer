"""Post-publish manifest gate.

A run of ``jobpipe fetch → normalise → publish`` is considered "passing"
by the upstream workflow if it produces *any* non-empty postings frame.
That bar is too low: on 2026-05-15 a refresh shipped with one healthy
source and five silent zeros, and the workflow stayed green.

This module is the second gate. It reads ``manifest.json`` (written by
:mod:`jobpipe.duckdb_io`) and the same preset YAML that drove the run,
then asserts:

* total postings ≥ ``preset.gate.min_total_rows`` (default 20),
* every source declared ``enabled: true`` in the preset reported ≥ 1
  row in ``manifest.postings.source_counts`` (unless explicitly listed
  in ``preset.gate.allow_zero_sources``), and
* same for benchmarks *when* the manifest carries a ``benchmarks``
  block — a zero-benchmark run is not fatal per ``runner.py`` invariant.

Wired into ``refresh.yml`` as the step after publish; any issue raises
:class:`GateError` and fails the workflow. The fix-loop is "investigate
the source that flat-lined, then either patch the adapter or move it
into ``allow_zero_sources`` with a comment."
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jobpipe.runner import load_preset

DEFAULT_MIN_TOTAL_ROWS = 20


class GateError(RuntimeError):
    """Raised when the manifest fails one or more gate assertions."""


def _enabled_names(block: dict[str, Any] | None) -> list[str]:
    """Return the names of entries with ``enabled: true`` in a preset block."""
    if not isinstance(block, dict):
        return []
    return [name for name, cfg in block.items() if isinstance(cfg, dict) and cfg.get("enabled")]


def check_manifest(
    manifest: dict[str, Any],
    preset: dict[str, Any],
    *,
    min_total_rows: int,
    allow_zero_sources: set[str],
) -> list[str]:
    """Validate ``manifest`` against ``preset``; return human-readable issues.

    An empty list means the run passed. Each entry is one self-contained
    failure description suitable for logging line-by-line.
    """
    issues: list[str] = []

    postings = manifest.get("postings")
    if not isinstance(postings, dict):
        issues.append("manifest has no 'postings' block")
        return issues

    total = postings.get("row_count")
    if not isinstance(total, int) or total < min_total_rows:
        issues.append(f"total postings {total!r} below threshold {min_total_rows}")

    source_counts = postings.get("source_counts") or {}
    if not isinstance(source_counts, dict):
        issues.append("manifest.postings.source_counts is not a mapping")
        source_counts = {}

    for name in _enabled_names(preset.get("sources")):
        if name in allow_zero_sources:
            continue
        if int(source_counts.get(name, 0)) <= 0:
            issues.append(f"source {name}: zero rows in manifest")

    bench = manifest.get("benchmarks")
    if isinstance(bench, dict):
        bench_counts = bench.get("source_counts") or {}
        if not isinstance(bench_counts, dict):
            issues.append("manifest.benchmarks.source_counts is not a mapping")
            bench_counts = {}
        for name in _enabled_names(preset.get("benchmarks")):
            if name in allow_zero_sources:
                continue
            if int(bench_counts.get(name, 0)) <= 0:
                issues.append(f"benchmark {name}: zero rows in manifest")
    # If manifest has no `benchmarks` block at all, that's a zero-benchmark
    # run — not fatal per the runner's invariant. Stay silent.

    return issues


def _read_manifest(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise GateError(f"manifest not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise GateError(f"manifest {path} is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise GateError(f"manifest {path} must be a JSON object at the top level")
    return raw


def _gate_config(preset: dict[str, Any]) -> tuple[int, set[str]]:
    block = preset.get("gate") or {}
    if not isinstance(block, dict):
        raise GateError("preset 'gate' block must be a mapping")
    min_total = block.get("min_total_rows", DEFAULT_MIN_TOTAL_ROWS)
    if not isinstance(min_total, int) or min_total < 0:
        raise GateError(
            f"preset 'gate.min_total_rows' must be a non-negative integer, got {min_total!r}"
        )
    allow_raw = block.get("allow_zero_sources", []) or []
    if not isinstance(allow_raw, list):
        raise GateError("preset 'gate.allow_zero_sources' must be a list")
    return min_total, {str(n) for n in allow_raw}


def run_gate(manifest_path: Path, preset_path: Path) -> None:
    """CLI entry point. Raises :class:`GateError` on any failure."""
    manifest = _read_manifest(manifest_path)
    preset = load_preset(preset_path)
    min_total, allow_zero = _gate_config(preset)
    issues = check_manifest(
        manifest,
        preset,
        min_total_rows=min_total,
        allow_zero_sources=allow_zero,
    )
    if issues:
        raise GateError("manifest gate failed:\n  - " + "\n  - ".join(issues))
