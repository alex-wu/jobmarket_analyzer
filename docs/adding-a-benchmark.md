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

- **CSO Ireland (PxStat)** publishes via JSON-stat. Quarterly cadence, sector-level granularity.
- **OECD** uses SDMX. Annual cadence, country-level.
- **Eurostat** has a 4-year lag for the Structure of Earnings Survey. Flag this in the dashboard period column.
- All three are open-data; redistribution is allowed with attribution.
