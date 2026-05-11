# Third-Party Attributions

This project redistributes or queries data and code from third parties. Required attributions:

## Data sources

### Remotive

Job postings retrieved via the [Remotive Remote Jobs API](https://remotive.com/remote-jobs/api) are displayed with links back to the original Remotive listing. We do not redistribute the dataset; the dashboard surfaces title, location, salary range (where present), and a `posting_url` link.

### ESCO (European Skills, Competences, Qualifications and Occupations)

Occupation tagging uses the ESCO taxonomy, published by the European Commission under [EUPL 1.2](https://commission.europa.eu/content/european-union-public-licence_en) (with portions under Apache-2.0). We redistribute only the `(posting_id, isco_code)` join keys — not ESCO labels, descriptions, or skill graphs — in the published Parquet bundle. ESCO content remains the property of the European Union and is used here in accordance with Commission Decision 2014/188/EU.

### Adzuna

Job postings retrieved via the [Adzuna API](https://developer.adzuna.com/) are surfaced with attribution and link-out to the original posting on Adzuna or the underlying advertiser.

### Hacker News Who's Hiring (via Algolia)

Job mentions parsed from monthly Hacker News "Who's Hiring" threads use the [Algolia HN Search API](https://hn.algolia.com/api). Original thread URLs are surfaced as the posting source.

### Greenhouse / Lever / Ashby / Personio public board APIs

Postings from public job-board endpoints of these ATS providers are surfaced with links back to the original career page. No private endpoints, authentication, or proprietary data is accessed.

### Statistical agencies

Salary benchmark series are sourced from:
- [CSO Ireland (Central Statistics Office) PxStat](https://data.cso.ie/) — Open Data
- [OECD Data Explorer (SDMX API)](https://data-explorer.oecd.org/) — Open Data
- [Eurostat](https://ec.europa.eu/eurostat) — Open Data

All three publish under permissive open-data terms allowing redistribution with attribution.

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
