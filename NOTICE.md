# Third-Party Attributions

This project redistributes or queries data and code from third parties. Required attributions:

## Data sources

### ESCO (European Skills, Competences, Qualifications and Occupations)

Occupation tagging uses the ESCO taxonomy v1.2.1 (released 2025-12-10); skill tagging uses ESCO Pillar B v1.1.1. Both are published by the European Commission under the **European Union Public Licence v1.2 (EUPL-1.2)** with portions under Apache-2.0. ESCO content remains the property of the European Union and is used here in accordance with Commission Decision 2014/188/EU.

This project redistributes a derived subset of ESCO in three places, all under EUPL-1.2:

1. **`config/esco/isco08_labels.parquet`** — 2 137 labels mapped to ISCO-08 4-digit codes. For each 4-digit unit group it contains the group's preferred label (from the ISCO concept) plus the `title` field of each narrower occupation listed under it. Built by `scripts/build_esco_snapshot.py` walking the public REST API (ADR-010); see `config/esco/README.md` for provenance.
2. **`config/esco/skills_labels.parquet`** — 13 896 ESCO Pillar B skill/knowledge concepts, built by `scripts/build_esco_skills_snapshot.py` from the [`tabiya-tech/tabiya-open-dataset`](https://github.com/tabiya-tech/tabiya-open-dataset) mirror of ESCO **v1.1.1** (ADR-023). Thanks to Tabiya for maintaining the open mirror.
3. **`(posting_id, isco_code, isco_match_method, isco_match_score)` and `skills`** — the ISCO columns and the ESCO-derived `skills` list on every posting row in the published Parquet bundle. These are factual annotations rather than ESCO content.

> "European Skills, Competences, Qualifications and Occupations (ESCO) classification versions 1.2.1 (occupations) and 1.1.1 (skills), © European Union, 2025. Licensed under EUPL-1.2."

### Adzuna

Job postings retrieved via the [Adzuna API](https://developer.adzuna.com/) are surfaced with attribution and link-out to the original posting on Adzuna or the underlying advertiser.

### Greenhouse / Lever / Ashby / Personio public board APIs (shelved in v1)

ATS adapters are shelved per ADR-017 (`enabled: false`) — v1 fetches nothing from these providers. If re-enabled: postings from public job-board endpoints are surfaced with links back to the original career page. No private endpoints, authentication, or proprietary data is accessed.

### Statistical agencies (shelved in v1)

Benchmark adapters are shelved per ADR-017 (`enabled: false`) — v1 fetches and redistributes nothing from these agencies. Attribution retained for reactivation:
- **CSO Ireland (Central Statistics Office) PxStat** — `https://data.cso.ie/`. Cube `EHQ03` (Earnings, Hours and Employment Costs Survey, quarterly). Open Data under CSO's [Re-use of Public Sector Information policy](https://www.cso.ie/en/aboutus/dataprotection/reuseofdata/). Caveat: CSO does NOT publish 4-digit ISCO; the cube exposes a 3-bucket "Type of Employee" axis, surfaced in the dashboard with appropriate documentation (ADR-012).
- **OECD SDMX** — `https://sdmx.oecd.org/`. Adapter implemented but currently disabled (Cloudflare bot-protection blocks anonymous CI access — ADR-011). When re-enabled it will be cited per the [OECD Terms and Conditions](https://www.oecd.org/termsandconditions/).
- **Eurostat** — `https://ec.europa.eu/eurostat`. Dataset `earn_ses_annual` (Structure of Earnings Survey, annual earnings, rebased every four years). Open Data under the [Eurostat free re-use policy](https://ec.europa.eu/eurostat/about/policies/copyright).

All three publish under permissive open-data terms allowing redistribution with attribution. If re-enabled, the dashboard will surface attribution per series alongside the data points.

## Software libraries

This project depends on the following open-source software (full list in `pyproject.toml` / `uv.lock`). Notable redistributables:

- **DuckDB** — MIT
- **DuckDB-WASM** — MIT
- **Observable Framework** — Apache-2.0
- **pandera** — MIT
- **rapidfuzz** — MIT
- **httpx** — BSD-3-Clause
- **pydantic** / **pydantic-settings** — MIT
- **typer** — MIT
- **OpenAI Python SDK** — Apache-2.0

Each library's own LICENSE applies to its code. This NOTICE is informational.
