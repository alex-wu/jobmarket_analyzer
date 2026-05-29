# Adzuna API — local reference

> Built from a live probe of the API on **2026-05-18** combined with the public
> docs at <https://developer.adzuna.com/overview> and the interactive Swagger UI
> at <https://developer.adzuna.com/activedocs> (JS-rendered — can't be scraped
> headlessly, so this doc records what the wire actually returned).
>
> Source of truth for our adapter: `src/jobpipe/sources/adzuna.py`.
> Raw probe captures: `tmp/adzuna_probe.json`, `tmp/adzuna_probe2.json`
> (gitignored — re-run via `tmp/_adzuna_probe.py` / `_adzuna_probe2.py`).

---

## 1. Authentication & base URL

```
Base: https://api.adzuna.com/v1/api
Auth: query-string app_id + app_key on every request
Format: append `content-type=application/json` (also: xml)
```

Free-tier quota and rate limits are not publicly documented. Our adapter caps
itself at `max_pages * results_per_page` per `fetch()` call and the refresh
workflow honours `min_interval_hours: 24` (currently weekly per ADR-018).

---

## 2. Country coverage (2026)

`at au be br ca ch de es fr gb in it mx nl nz pl sg us za` — 19 countries.
**Ireland (`ie`) is NOT served by Adzuna.** Our current preset
`data_analyst_eu` uses `gb + es`.

---

## 3. Endpoints (all probed 2026-05-18, all returned 200 except where noted)

| Endpoint | Purpose | Status |
|---|---|---|
| `GET /jobs/{country}/search/{page}` | Job postings list | ✅ — adapter uses |
| `GET /jobs/{country}/details/{id}` | Full description for one posting | ✅ — work_arrangement enrichment uses |
| `GET /jobs/{country}/categories` | List of 27 Adzuna categories for country | ✅ — unused |
| `GET /jobs/{country}/top_companies` | Leaderboard of companies for a query | ✅ — unused |
| `GET /jobs/{country}/geodata` | Posting counts by region/city | ✅ — unused |
| `GET /jobs/{country}/histogram` | Salary distribution histogram | ✅ — unused |
| `GET /jobs/{country}/history` | 12-month monthly average salary | ✅ — unused |

There is also a `GET /version` endpoint (we didn't need it).

### 3a. `GET /jobs/{country}/details/{id}` — full posting body

Schema-v3 work-arrangement enrichment (`src/jobpipe/work_arrangement/fetcher.py`)
fetches one description per posting to recover the full body (the `/search`
response truncates `description` to ~500 chars + ellipsis). The `id` is the
same value as `raw_payload["id"]` carried through the search response.

Request params — same as search: `app_id`, `app_key`, `content-type=application/json`.

Response payload mirrors a single search-result entry. The relevant field
is `description` (string, untruncated). 404 indicates the posting has been
purged upstream (closed/expired) between the search call and the details
call — handled by the fetcher as a silent NULL classification, written to
the disk cache as empty so it isn't retried.

The fetcher caps inter-call sleep at 0.5s and persists each body to
`data/cache/work_arrangement/{posting_id}.txt`, so steady-state quota
drops sharply once the cache warms (Run-4 hit rate ~80% on the active
preset). The first publish on a fresh checkout will issue one call per
unique posting (~1k for the active gb+es preset).

---

## 4. `GET /jobs/{country}/search/{page}` — request parameters

Empirically confirmed on `gb` (2026-05-18). Server rejects unknown params with
HTTP 400 + a generic Chef error page, so the table below lists ONLY what the
API actually accepts.

| Param | Type | Default | Notes |
|---|---|---|---|
| `app_id` | str | — | **Required** |
| `app_key` | str | — | **Required** |
| `results_per_page` | int | 10 | Max 50 (adapter pins to 50) |
| `what` | str | — | Free-text keyword search |
| `what_and` | str | — | Space-separated tokens, AND join |
| `what_or` | str | — | Space-separated tokens, OR join |
| `what_phrase` | str | — | Exact phrase match |
| `what_exclude` | str | — | Negative keywords |
| `title_only` | str | — | Restrict keyword match to the job title |
| `where` | str | — | Place name (e.g. "London"). When set, `latitude`/`longitude` are **omitted** from results — see §5 |
| `distance` | int (km) | — | Radius around `where` |
| `location0`, `location1` | str | — | Hierarchical location filter. `location0=UK&location1=London` works. `location2` → **HTTP 400** (only depth 0/1 accepted on `gb`) |
| `category` | str | — | Adzuna category `tag` from `/categories` (e.g. `it-jobs`) |
| `company` | str | — | Filter to a single company display name |
| `max_days_old` | int | — | Cap posting age in days (adapter uses this) |
| `salary_min` | int | — | Native currency |
| `salary_max` | int | — | Native currency |
| `salary_include_unknown` | 0/1 | 0 | When `1`, include postings with missing salary |
| `full_time` | 0/1 | — | Only `1` is meaningful (set to filter) |
| `part_time` | 0/1 | — | Same |
| `permanent` | 0/1 | — | Same |
| `contract` | 0/1 | — | Same |
| `sort_by` | enum | (server default) | Confirmed values: `date`, `salary`, `relevance`. `default` / `hybrid` → **HTTP 400** |
| `sort_direction` | `up`/`down` | down | Used with `sort_by=salary` |
| `content-type` | str | xml | We pass `application/json` |

---

## 5. `GET /jobs/{country}/search/{page}` — response schema

Top-level (observed):

```json
{
  "__CLASS__": "Adzuna::API::Response::JobSearchResults",
  "count": 808559,                       // total matching postings
  "mean": 53086.72,                      // mean salary across the matching set (only when `what` is set)
  "results": [ Job, Job, ... ]
}
```

`Job` object (union of all observed keys across multiple probes):

| Field | Type | Always present? | Notes |
|---|---|---|---|
| `id` | str | yes | Adzuna posting id |
| `title` | str | yes | |
| `description` | str | yes | **Hard-truncated to 500 chars** + the U+2026 ellipsis (`…`). Cannot be expanded via any documented param. See §8. |
| `created` | ISO 8601 str | yes | Posting publish time, UTC |
| `redirect_url` | str | yes | Deep link to `adzuna.co.uk/jobs/land/ad/…` with our `utm_source` baked in |
| `adref` | JWT-like str | yes | Click-attribution token. Only needed if we forward users via Adzuna's click-tracking — we don't |
| `category.tag` | str | yes | e.g. `it-jobs` — Adzuna taxonomy slug |
| `category.label` | str | yes | e.g. `IT Jobs` |
| `company.display_name` | str | yes | Recruiter or hiring company |
| `location.display_name` | str | yes | e.g. `London, UK` |
| `location.area[]` | str[] | yes | Hierarchy: e.g. `["UK", "South East England", "Hampshire", "Fareham", "Stubbington"]` — up to 5 levels |
| `salary_min` | number | almost always | Native currency. `0` when unknown for some postings |
| `salary_max` | number | almost always | Same |
| `salary_is_predicted` | `"0"`/`"1"` (str) | yes | `"1"` = Adzuna imputed the salary from similar postings |
| `contract_type` | enum str | sometimes | `permanent`, `contract` (other values likely exist) |
| `contract_time` | enum str | sometimes | `full_time`, `part_time` |
| `latitude` | float | **conditional** | Present when `where` is NOT set; omitted when results are spatially pre-filtered |
| `longitude` | float | **conditional** | Same |

`__CLASS__` keys are Adzuna internal type markers — safe to ignore.

---

## 6. Other endpoints — schemas

### `/jobs/{country}/categories`

```json
{
  "results": [
    { "tag": "accounting-finance-jobs", "label": "Accounting & Finance Jobs" },
    { "tag": "it-jobs", "label": "IT Jobs" },
    ...
  ]
}
```

27 categories on `gb`. Stable taxonomy — cache and treat as static.

### `/jobs/{country}/top_companies?what=<query>`

```json
{
  "leaderboard": [
    { "canonical_name": "Cognizant Technology Solutions", "count": 21 },
    { "canonical_name": "Relay Technologies", "count": 16 },
    ...
  ]
}
```

`canonical_name` is Adzuna's normalised company name (different from
`Job.company.display_name`, which is the recruiter-supplied raw name). Useful
for company-side dedupe.

### `/jobs/{country}/geodata?category=<tag>` (or `?what=<query>`)

```json
{
  "locations": [
    {
      "location": { "display_name": "London, UK", "area": ["UK", "London"] },
      "count": 16511
    },
    ...
  ]
}
```

Counts of currently-active postings by region. Useful for a regional choropleth
without paying per-row fetch.

### `/jobs/{country}/histogram?what=<query>`

```json
{
  "histogram": { "10000": 2, "20000": 54, "30000": 108, "40000": 161, ... }
}
```

Salary distribution bucketed by `floor(salary / 10_000) * 10_000`, native
currency. Counts are over the matching set.

### `/jobs/{country}/history?what=<query>`

```json
{
  "what": "data analyst",
  "month": {
    "2025-05": 51967.04, "2025-06": 51291.08, ..., "2026-04": 57160.24
  }
}
```

12 months of monthly average advertised salary, native currency. Cheap
benchmark.

---

## 7. What our adapter consumes today vs what's untapped

`src/jobpipe/sources/adzuna.py:_normalise_row` maps these Job fields → PostingSchema:

| Adzuna field | → PostingSchema | Note |
|---|---|---|
| `id` | → `posting_id` (sha1 of `adzuna:<id>`) | |
| `title` | → `title` | |
| `company.display_name` | → `company` | We do NOT use `top_companies.canonical_name` for dedupe |
| `location.display_name` | → `location_raw` | We DROP `location.area[]` — the hierarchy is in `raw_payload` only |
| `salary_min`, `salary_max` | → `salary_min_eur`, `salary_max_eur` | Native cur. → EUR happens in `normalise.run` |
| `salary_is_predicted` | → `salary_imputed` | |
| `created` | → `posted_at` | |
| `redirect_url` | → `posting_url` | |
| (entire raw) | → `raw_payload` (JSON str) | All untapped fields survive here |

**Dropped (available in `raw_payload` but unused):**

- `description` — 500 chars of free text per posting
- `category.{tag,label}` — Adzuna's 27-bucket taxonomy
- `contract_type`, `contract_time` — permanent/contract + full_time/part_time
- `latitude`, `longitude` — when `where` is unset
- `location.area[]` — full hierarchy path
- `adref` — only matters for click-attribution

**Endpoints we never call:**
`/categories`, `/top_companies`, `/geodata`, `/histogram`, `/history`.

---

## 8. Enrichment candidates — ranked by leverage

Each candidate is something we could add without paying for any new data source
beyond what Adzuna already returns. Ranked by ratio of (dashboard insight
unlocked) ÷ (implementation cost).

| # | Enrichment | Source | Cost | Insight unlocked |
|---|---|---|---|---|
| 1 | **Persist `category.tag`** on PostingSchema | Already in the search response | 1 column add + 1 line of normalise + schema migration | Adzuna taxonomy as a sanity check against ISCO — fills the ~40% of rows where `isco_match_method = none`. Cross-tab Adzuna category × ISCO major to validate matcher. |
| 2 | **Persist `contract_type` + `contract_time`** | Search response | 2 column adds + normalise | Permanent vs contract salary delta is a dashboard panel users will ask for. Currently lost. |
| 3 | **Persist `latitude` / `longitude`** (when present) | Search response | 2 column adds; preset drop `where` for at least one keyword so geo is returned | Region-level map without geocoding. Note ~50% blank for current preset because we use `where=` — would need preset rework. |
| 4 | **Skill extraction from `description`** | Search response (500 chars) | New `enrich` stage; regex/SkillNer/simple keyword list | Top-N skills per role/country panel. 500-char ceiling means we get title + first paragraph only — still enough for stack-keyword frequency. |
| 5 | **Side-table: `/history` benchmark** per (country, keyword) | `/history` endpoint, 1 call per preset keyword | New `benchmarks` adapter, weekly write to `benchmarks.parquet` | Trend line: "Adzuna 12-month avg salary for X" vs our observed dataset — directly answers "is the market hotter/cooler". |
| 6 | **Side-table: `/histogram` benchmark** per (country, keyword) | `/histogram` endpoint | Same | Salary distribution overlay on our salary panel. Lets us show our sample alongside Adzuna's full distribution. |
| 7 | **Side-table: `/geodata` benchmark** per (country, category) | `/geodata` endpoint | Same | Regional posting density without fetching every posting. |
| 8 | **Use `top_companies.canonical_name`** for company dedupe | `/top_companies` endpoint, 1 call per (country, keyword) | Join-table in normalise | "Robert Half" / "Robert Half Technology" / "Robert Half Talent" collapse. Today they're separate rows. |
| 9 | **`location.area[]` hierarchy** | Search response | 1 column (json array) + normalise | Drill-down: country → region → city without geocoding. Cheaper than (3). |
| 10 | **`mean` (top-level search response)** | Already in response we throw away | Capture into manifest only | Sanity check: our scraped salary mean vs Adzuna's reported mean. Detects under-sampling. |

---

## 9. Known pitfalls / gotchas

- **Strict param validation** — any unknown query param → HTTP 400 with a Chef
  error HTML page (not JSON). Future param additions must be probed first.
- **`sort_by` valid values are `date`, `salary`, `relevance` only.**
  `default` and `hybrid` both 400. Adapter uses no `sort_by` (relies on
  Adzuna's default).
- **`location` hierarchy depth caps at 1 on `gb`.** `location2` → 400. May
  differ per country.
- **`description` is truncated to 500 chars** with a U+2026 ellipsis. There is
  no `?full_description=1` flag. Full JD only available by scraping
  `redirect_url`'s landing page — which is against ToS without a partnership.
- **`latitude`/`longitude` are conditionally returned.** Present when results
  span the country (no `where=` filter); omitted when geographic pre-filter is
  applied. Our `data_analyst_eu` preset doesn't use `where`, so we'd see them
  if we captured them — currently they're dropped at normalise.
- **`salary_is_predicted` is a STRING `"0"`/`"1"`** not a bool. Adapter
  coerces with `bool(int(str(v)))` — handle missing-value path
  (`None` → `None`, not `False`).
- **`salary_min` can be `0`** for some postings (not `null`). Treat `<= 0` as
  unknown when persisting. The site loader's `WHERE salary_annual_eur_p50 IS
  NULL OR > 0` predicate already does this for the derived field.
- **`count` is "total matching postings", not "returned"** — useful for
  estimating how many pages exist but don't substitute it for `len(results)`.

---

## 10. Re-probing later

```powershell
# Re-runs both probes; output to tmp/adzuna_probe*.json
uv run python tmp/_adzuna_probe.py  > tmp/adzuna_probe.json
uv run python tmp/_adzuna_probe2.py > tmp/adzuna_probe2.json
```

Both scripts read creds from `.env` directly (no dotenv import), so they're
safe to run without `dotenv` installed and won't pull from `os.environ` if
`.env` is missing — they'll raise `KeyError` instead, which is the desired
behaviour.

The `tmp/` directory is gitignored (per `.gitignore`). Probes are for local
verification only — do not commit raw payloads with our app_id/app_key in URLs.
