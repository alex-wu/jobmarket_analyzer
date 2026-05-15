---
title: Job Market Analyzer
toc: false
---

# Job Market Analyzer

```js
import * as Plot from "npm:@observablehq/plot";
import * as Inputs from "npm:@observablehq/inputs";
import {DuckDBClient} from "npm:@observablehq/duckdb";
import {html} from "npm:htl";
import {coverageNote} from "./components/coverageNote.js";
import {kpiCard} from "./components/kpiCard.js";
import {barChart} from "./components/barChart.js";
import {heatmap} from "./components/heatmap.js";
import {countrySelect, iscoMajorSelect, salaryRange, dateRange, whereClause, andClause, ALL} from "./components/filters.js";
import {iscoMajorLabel} from "./components/isco.js";

const manifest = await FileAttachment("data/manifest.json").json();
const db = await DuckDBClient.of({postings: FileAttachment("data/postings.parquet")});
```

```js
const countries = Array.from(
  await db.query(`SELECT DISTINCT country FROM postings WHERE country IS NOT NULL ORDER BY 1`),
  (r) => r.country
);
const iscoPresent = Array.from(
  await db.query(`SELECT DISTINCT isco_major FROM postings WHERE isco_major IS NOT NULL ORDER BY 1`),
  (r) => r.isco_major
);
const allDates = await db.queryRow(`SELECT MIN(posted_at) AS lo, MAX(posted_at) AS hi FROM postings WHERE posted_at IS NOT NULL`);
```

```js
function fmtDate(v) {
  if (v == null) return "—";
  const d = v instanceof Date ? v : new Date(v);
  if (isNaN(d)) return "—";
  return d.toLocaleDateString("en-GB", {year: "numeric", month: "short", day: "2-digit"});
}
```

<small>
EU data-analyst preset · daily snapshot ·
as of <strong>${fmtDate(manifest.generated_at)}</strong> ·
<strong>${manifest.postings.row_count.toLocaleString()}</strong> postings ·
<strong>${Object.keys(manifest.postings.country_counts).length}</strong> countries ·
pipeline <code>${manifest.pipeline_version}</code>
</small>

A no-backend, browser-side dashboard. Parquet ships from a GitHub Release; charts run in-browser via DuckDB-WASM. Filter once at the top — every chart re-flows.

## Filter

```js
const country = view(countrySelect(countries));
const isco    = view(iscoMajorSelect(iscoPresent));
const salary  = view(salaryRange(0, 250000));
const dates   = view(dateRange([allDates.lo, allDates.hi]));
```

```js
const where = whereClause({country, iscoMajor: isco, salary, dates});
```

```js
const live = await db.queryRow(`
  SELECT COUNT(*)::INT AS n,
         COUNT(salary_annual_eur_p50)::INT AS n_salary,
         COUNT(isco_code)::INT AS n_isco
  FROM postings ${where}
`);
display(coverageNote(manifest, {n: live.n, nSalary: live.n_salary, nIsco: live.n_isco}));
```

<div class="grid grid-cols-4">
  ${kpiCard("Postings", live.n.toLocaleString(), `of ${manifest.postings.row_count.toLocaleString()} in snapshot`)}
  ${kpiCard("With salary", live.n ? `${Math.round((live.n_salary / live.n) * 100)}%` : "—", `${live.n_salary.toLocaleString()} disclose €p50`)}
  ${kpiCard("ISCO-tagged", live.n ? `${Math.round((live.n_isco / live.n) * 100)}%` : "—", "rapidfuzz cutoff 85")}
  ${kpiCard("Date span", fmtDate(allDates.lo), `→ ${fmtDate(allDates.hi)}`)}
</div>

## Salary distribution

```js
const salaryRows = Array.from(await db.query(`
  SELECT salary_annual_eur_p50 AS salary
  FROM postings
  ${andClause(where)} salary_annual_eur_p50 IS NOT NULL
`));
```

```js
const byCountry = Array.from(await db.query(`
  SELECT country,
         quantile_cont(salary_annual_eur_p50, 0.5) AS p50,
         COUNT(salary_annual_eur_p50)::INT AS n
  FROM postings
  ${andClause(where)} salary_annual_eur_p50 IS NOT NULL
  GROUP BY 1
  ORDER BY 2 DESC
`));
```

<div class="grid grid-cols-2">
  <div class="card">
    <h2>Annual salary histogram</h2>
    ${salaryRows.length === 0
      ? html`<div>No salary data in current selection.</div>`
      : resize((width) => Plot.plot({
          width,
          height: 260,
          marginLeft: 50,
          x: {label: "Annual €p50", grid: true, tickFormat: (v) => `€${(v / 1000).toFixed(0)}k`},
          y: {label: "Postings", grid: true},
          marks: [
            Plot.rectY(salaryRows, Plot.binX({y: "count"}, {x: "salary", tip: true, thresholds: 24})),
            Plot.ruleY([0])
          ]
        }))}
  </div>
  <div class="card">
    <h2>Median salary by country</h2>
    ${byCountry.length === 0
      ? html`<div>No country breakdown in current selection.</div>`
      : resize((width) => barChart(byCountry, {
          x: "p50",
          y: "country",
          xLabel: "Median €p50",
          xTickFormat: (v) => `€${(v / 1000).toFixed(0)}k`,
          marginLeft: 50,
          height: 260,
          width
        }))}
  </div>
</div>

## Roles & occupations

```js
const titles = Array.from(await db.query(`
  SELECT title, COUNT(*)::INT AS n
  FROM postings
  ${andClause(where)} title IS NOT NULL
  GROUP BY 1
  ORDER BY 2 DESC
  LIMIT 15
`));
```

```js
const iscoMix = Array.from(
  await db.query(`
    SELECT COALESCE(isco_major, '∅') AS isco_major,
           COUNT(*)::INT AS n
    FROM postings ${where}
    GROUP BY 1
    ORDER BY 2 DESC
  `),
  (d) => ({...d, label: d.isco_major === "∅" ? "Unclassified" : iscoMajorLabel(d.isco_major)})
);
```

<div class="grid grid-cols-2">
  <div class="card">
    <h2>Top 15 titles</h2>
    ${titles.length === 0
      ? html`<div>No titles in current selection.</div>`
      : resize((width) => barChart(titles, {x: "n", y: "title", xLabel: "Postings", marginLeft: 220, height: 380, width}))}
  </div>
  <div class="card">
    <h2>ISCO-08 major group mix</h2>
    ${iscoMix.length === 0
      ? html`<div>No ISCO breakdown in current selection.</div>`
      : resize((width) => barChart(iscoMix, {
          x: "n",
          y: "label",
          xLabel: "Postings",
          marginLeft: 220,
          height: 380,
          width
        }))}
  </div>
</div>

## Country × ISCO median salary

```js
const heatRows = Array.from(
  await db.query(`
    SELECT country,
           isco_major,
           quantile_cont(salary_annual_eur_p50, 0.5) AS p50,
           COUNT(salary_annual_eur_p50)::INT AS n
    FROM postings
    ${andClause(where)} salary_annual_eur_p50 IS NOT NULL AND isco_major IS NOT NULL
    GROUP BY 1, 2
    HAVING COUNT(*) >= 3
    ORDER BY 1, 2
  `),
  (d) => ({...d, iscoLabel: iscoMajorLabel(d.isco_major)})
);
```

<div class="card">
  ${heatRows.length === 0
    ? html`<div>Heatmap needs at least 3 salaried + ISCO-tagged postings per cell. Loosen the filter to see it populate.</div>`
    : resize((width) => heatmap(heatRows, {
        x: "country",
        y: "iscoLabel",
        value: "p50",
        valueLabel: "Median €p50",
        valueFormat: (v) => `€${(v / 1000).toFixed(0)}k`,
        marginLeft: 220,
        height: Math.max(220, 36 * new Set(heatRows.map((d) => d.iscoLabel)).size),
        width
      }))}
</div>

## Posting cadence

```js
const weekly = Array.from(await db.query(`
  SELECT date_trunc('week', posted_at::TIMESTAMP)::DATE AS wk,
         COUNT(*)::INT AS n
  FROM postings
  ${andClause(where)} posted_at IS NOT NULL
  GROUP BY 1
  ORDER BY 1
`));
```

<div class="card">
  ${weekly.length === 0
    ? html`<div>No postings in current selection.</div>`
    : resize((width) => Plot.plot({
        width,
        height: 240,
        marginLeft: 50,
        x: {label: null, type: "time"},
        y: {label: "Postings / week", grid: true},
        marks: [
          Plot.areaY(weekly, {x: "wk", y: "n", fillOpacity: 0.2, curve: "monotone-x"}),
          Plot.lineY(weekly, {x: "wk", y: "n", curve: "monotone-x"}),
          Plot.dot(weekly, {x: "wk", y: "n", r: 3, tip: true}),
          Plot.ruleY([0]),
          Plot.crosshairX(weekly, {x: "wk", y: "n"})
        ]
      }))}
</div>

<small>Week buckets are <code>date_trunc('week', posted_at)</code>; the first and last weeks are usually partial.</small>

## Sources & methodology {#sources}

```js
const sources = Array.from(await db.query(`
  SELECT source, COUNT(*)::INT AS n
  FROM postings ${where}
  GROUP BY 1
  ORDER BY 2 DESC
`));
```

<div class="grid grid-cols-2">
  <div class="card">
    <h2>Sources in this selection</h2>
    ${Inputs.table(sources, {columns: ["source", "n"], header: {source: "Source", n: "Postings"}, width: {n: 90}})}
  </div>
  <div class="card">
    <h2>Pipeline manifest</h2>
    ${Inputs.table(
      [
        {field: "preset_id", value: manifest.preset_id ?? "—"},
        {field: "run_id", value: manifest.run_id ?? "—"},
        {field: "git_sha", value: manifest.git_sha ?? "—"},
        {field: "pipeline_version", value: manifest.pipeline_version ?? "—"},
        {field: "schema_version", value: manifest.schema_version ?? "—"},
        {field: "generated_at", value: manifest.generated_at ?? "—"}
      ],
      {header: {field: "Field", value: "Value"}}
    )}
  </div>
</div>

**What this is.** A static dashboard over a daily snapshot of EU data-analyst job postings, normalised + tagged by [`jobmarket_analyzer`](https://github.com/alex-wu/jobmarket_analyzer). Pipeline runs at 06:00 UTC on GitHub Actions, writes a single `postings.parquet` to the `latest` release, and this page reads that artefact in-browser via DuckDB-WASM. No backend, no API key.

**What's deliberately not on this dashboard.** The original spec called for `experience_level`, `work_arrangement` (remote / hybrid / on-site), and `skills` facets. None live in the current `PostingSchema`. We ship only on fields we have, with explicit coverage annotations rather than guessing. Full extraction roadmap: [`docs/dashboard_data_gaps.md`](https://github.com/alex-wu/jobmarket_analyzer/blob/main/docs/dashboard_data_gaps.md). Dashboard architecture: [`docs/dashboard_strategy.md`](https://github.com/alex-wu/jobmarket_analyzer/blob/main/docs/dashboard_strategy.md).

**Tech.** Observable Framework for the shell + reactive runtime · DuckDB-WASM for in-browser SQL on the parquet · Observable Plot for charts (stock marks only) · Pandera for upstream `PostingSchema` strict-mode validation.

**Refresh.** The `refresh.yml` cron runs daily at 06:00 UTC. Refresh the local sample with:

```bash
gh release download latest \
  -p "postings__postings.parquet" -p "manifest.json" \
  -R alex-wu/jobmarket_analyzer \
  -D data/gh_databuild_samples/ --clobber
```
