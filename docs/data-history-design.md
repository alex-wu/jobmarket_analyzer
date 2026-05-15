# Data history design — accumulating 6-month corpus

**Status:** design only. Not implemented. Written during P9 cleanup
(2026-05-15) to document current behaviour and lay out the path forward.

## Current behaviour (snapshot-only)

The pipeline emits **daily snapshots** of the current corpus. Each run
fetches the full set of postings matching the preset query, then publishes
a complete artifact.

### Code trace

- `src/jobpipe/runner.py` — `fetch_sources()` (line 95-) fans out to enabled
  adapters. Each adapter returns the **full current set** of postings
  matching the preset query. Adzuna (`src/jobpipe/sources/adzuna.py`)
  respects `max_days_old: 180` upstream.
- `src/jobpipe/normalise.py` — applies `since_days` filter; drops rows older
  than `now - 180 days`. Cross-source dedup via `dedupe.cross_source()`
  using normalized URL → fallback title+company+country hash.
- `src/jobpipe/duckdb_io.py` — `export_bundle()` writes a single Parquet
  (no partitioning per ADR-014). `manifest.json` records `run_id`,
  `generated_at`, `posting_count` — **no rolling-window metadata.**
- `refresh.yml` — uploads to BOTH `latest` (clobbered every run) AND
  `data-YYYY-MM-DD` (immutable, idempotent per UTC day).
- `site/src/data/postings.parquet.js` — reads ONLY `latest`; never unions
  dated releases.

### Result

- 365 dated releases/year accumulate as a side effect, but the dashboard
  never sees them. They're effectively a free archive that nobody reads.
- Schema HAS the right timestamps already:
  - `posted_at` — upstream-stable (the date the job board published the role).
  - `ingested_at` — our fetch timestamp; advances on each daily re-appearance.

## Target behaviour (accumulating)

### Weekly cadence

Change `refresh.yml:5`:

```diff
-    - cron: "0 6 * * *"   # 06:00 UTC daily
+    - cron: "0 6 * * 1"   # 06:00 UTC every Monday
```

| Axis | Daily | Weekly |
|---|---|---|
| Dated releases/yr | 365 | 52 |
| Trend granularity | Daily | Weekly |
| Adzuna API quota | ~365 fetches/yr | ~52 fetches/yr (7× cheaper) |
| Cron-failure surface | 365 chances/yr | 52 |
| Freshness | ≤24h stale | ≤7d stale |
| Dashboard accuracy | Daily-fresh | Weekly-fresh |

Weekly is the right cost/value trade for a portfolio analytics dashboard.

### 6-month rolling accumulation

At publish time, union the last 26 weekly dated releases into one
accumulated parquet. Dedup by `posting_id`. Preserve **earliest**
`ingested_at` as `first_seen_at`, **latest** as `last_seen_at`.

This gives the dashboard a 130k-row dataset (~5k postings × 26 weeks) with
two new columns enabling trend analysis:

- `first_seen_at` — when our pipeline first observed the posting. Use this
  as the canonical "new posting" date for monthly-volume charts.
- `last_seen_at` — when we last observed it open. `last_seen_at <
  manifest.generated_at` signals upstream closure.

## Files that would change

Not in P9. Listed here for the implementation phase.

1. **`src/jobpipe/duckdb_io.py`** — add `export_accumulated(releases: list[Path], out: Path)`:
   - Read each dated release's parquet.
   - Union with `UNION ALL BY NAME`.
   - Dedup via DuckDB SQL: `GROUP BY posting_id`, `MIN(ingested_at) AS first_seen_at`, `MAX(ingested_at) AS last_seen_at`, `ANY_VALUE(other_cols)`.
   - Write single accumulated parquet.

2. **`src/jobpipe/runner.py`** — extend `run_publish()`:
   - Optional `--accumulate-weeks N` flag (default unset → current snapshot behaviour).
   - When set: shell out to `gh release list` filtered to `data-*` tags within the window, download each, call `export_accumulated()`.

3. **`config/runs/data_analyst_ireland.yaml`** — add:
   ```yaml
   publish:
     accumulate_weeks: 26
   ```

4. **`site/src/data/postings.parquet.js`** — name unchanged; payload is now the accumulated artifact. No dashboard-side code changes needed unless we add `first_seen_at`/`last_seen_at` visualisations (then P12-ish).

5. **`.github/workflows/refresh.yml`** — Publish step picks up the new preset flag automatically. No workflow YAML change needed.

6. **`docs/architecture.md`** — replace "snapshot per run" wording with the accumulation model.

## Open design questions (resolve before implementing)

- **A posting disappears upstream.** Keep with `last_seen_at` stale, OR drop. **Recommended: keep.** Closure history is a feature, not a bug, for trend analysis.
- **Schema migration.** Existing dated releases don't have `first_seen_at`. On first accumulated build, derive it from the earliest dated release that contains each `posting_id`. Backfill is one-time at first run.
- **Trend chart UX.** What does "monthly posting volume" mean when a single posting can persist 6 months? **Recommended: use `first_seen_at`** as the canonical "new posting" date. `last_seen_at` powers a separate "still-open jobs" panel.
- **Posting_id stability.** If the dedup key changed between releases (e.g. URL normalisation rules tweaked), the same posting can have two IDs across the window. Mitigation: pin the dedup hash function version; bump only at major-release boundaries.
- **Storage of dated releases.** GitHub Releases don't auto-prune. 52/yr × 5k postings × ~5kB = ~1.3 GB/yr. Acceptable for free tier. If pressure: prune dated releases > 13 months old via a `cleanup.yml` workflow.

## Trade-off vs the simpler alternative

A degenerate version of this design: just rename the dated releases to
weekly and have the dashboard read `latest` only. Loses trend analysis
entirely — back to single-snapshot. The accumulation step is the entire
value here.

## Why deferred

P9's scope is CI/CD modernisation, not pipeline rework. Accumulation
touches `runner.py` + `duckdb_io.py` + the publish step + the YAML preset
schema + dashboard data-loader semantics. It's its own phase. Tentatively
queue as **P10.5** or **P13** after P10 ships pipeline observability +
adapter coverage fixes.
