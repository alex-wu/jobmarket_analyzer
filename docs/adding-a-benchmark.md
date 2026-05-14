# Adding a new benchmark adapter

A benchmark adapter pulls official wage statistics from a statistics agency and emits a DataFrame conforming to [`BenchmarkSchema`](../src/jobpipe/schemas.py). It is the dashboard's reference line — postings vs. official median.

## Checklist

1. **Create the adapter module** under `src/jobpipe/benchmarks/<name>.py`. Same Protocol as sources: `name`, `config_model`, `fetch(config) -> pd.DataFrame`, decorated `@register("<name>")`.

2. **Map raw series → `BenchmarkSchema`.**
   - Join keys: `isco_code` (4-digit) + `country` (ISO-3166-1 alpha-2).
   - `period`: string label suitable for filtering ("2024-Q4", "2024", "2022-2024", ...).
   - Convert all currencies to EUR via `jobpipe.fx` (ECB rates).
   - `source_url`: required — every benchmark row links back to its source page.

3. **Record HTTP cassette + write unit test** (same pattern as source adapters; tests under `tests/benchmarks/`).

4. **Wire into the preset.** Add a block under `benchmarks:` in `config/runs/<preset>.yaml`.

5. **Document.**
   - Add an entry to the benchmarks list in `docs/architecture.md`.
   - Add attribution to `NOTICE.md` (statistics agencies typically require it).

## Worth knowing about EU benchmarks

- **CSO Ireland (PxStat)** publishes via JSON-stat. Quarterly cadence, sector-level granularity. Does NOT publish by 4-digit ISCO — the `EHQ03` cube exposes a 3-bucket "Type of Employee" axis (managers+profs / clerical+sales / manual). `cso.py` maps requested ISCO codes to the umbrella bucket by leading digit; document the coarseness in dashboard surfaces.
- **OECD** uses SDMX. Annual cadence, country-level. **Operational caveat:** `sdmx.oecd.org` is fronted by Cloudflare bot protection; unauthenticated GitHub-Actions calls return HTTP 403 + an HTML interstitial. The adapter handles this gracefully (logs and returns empty) but ships `enabled: false` in the preset until a workaround lands (auth header / CSV mirror / fixed-egress proxy).
- **Eurostat** has a 4-year lag for the Structure of Earnings Survey (`earn_ses_annual`); each vintage is rebased every four years. Flag this in the dashboard period column. ISCO codes ship with an `OC` prefix (`OC2511` etc.) — `eurostat.py` strips it and keeps only 4-digit leaves (aggregates like `OC25`, `OC1-5` are dropped).
- All three are open-data; redistribution is allowed with attribution.

## Throttling

The runner honours a per-benchmark `min_interval_hours` knob set on each
`BenchmarkConfig` subclass and overridable from the preset YAML. The
implementation reads the mtime of the newest parquet under
`data/raw/benchmarks/<name>/` and skips the fetch when the gap is under
the configured window. Choose your defaults to match the upstream cadence —
CSO is quarterly so `168h` (weekly recheck) is plenty; OECD/Eurostat are
annual so `720h` (monthly) avoids hammering them on the daily cron.

## Fail-isolation

`runner.fetch_benchmarks` catches anything an adapter raises, logs it, and
moves on. Schema validation failures are also caught at the runner boundary
so a malformed row from one adapter cannot poison the others. A run with
zero benchmark rows is acceptable — postings remain the primary signal
and the publish step keeps shipping.
