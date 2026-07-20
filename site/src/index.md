---
title: Overview
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
import {filterCard} from "./components/filterCard.js";
import {expandable} from "./components/expand.js";
import {whereClause, andClause} from "./components/filters.js";

const manifest = await FileAttachment("data/manifest.json").json();
const presets = await FileAttachment("data/presets.json").json();
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
${manifest.preset_id.replaceAll("_", " ")} preset · daily snapshot ·
as of <strong>${fmtDate(manifest.generated_at)}</strong> ·
<strong>${manifest.postings.row_count.toLocaleString()}</strong> postings ·
<strong>${Object.keys(manifest.postings.country_counts).length}</strong> countries ·
pipeline <code>${manifest.pipeline_version}</code>
</small>

A no-backend, browser-side dashboard. Parquet ships from a GitHub Release; charts run in-browser via DuckDB-WASM. Filter once at the top — every chart re-flows.

```js
const filters = view(filterCard({countries, iscoPresent, dateBounds: [allDates.lo, allDates.hi], presets}));
```

```js
const where = whereClause(filters);
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
function salaryHistogram(width, height = 260) {
  return Plot.plot({
    width,
    height,
    marginLeft: 50,
    x: {label: "Annual €p50", grid: true, tickFormat: (v) => `€${(v / 1000).toFixed(0)}k`},
    y: {label: "Postings", grid: true},
    marks: [
      Plot.rectY(salaryRows, Plot.binX({y: "count"}, {x: "salary", tip: true, thresholds: 24})),
      Plot.ruleY([0])
    ]
  });
}
```

${salaryRows.length === 0
  ? html`<div class="card"><h2>Annual salary histogram</h2><div>No salary data in current selection.</div></div>`
  : expandable(
      "Annual salary histogram",
      resize((width) => salaryHistogram(width)),
      (w, h) => salaryHistogram(w, h)
    )}

## Posting cadence

```js
const weekly = Array.from(await db.query(`
  SELECT date_trunc('week', posted_at::TIMESTAMP)::DATE AS wk,
         country,
         COUNT(*)::INT AS n
  FROM postings
  ${andClause(where)} posted_at IS NOT NULL AND country IS NOT NULL
  GROUP BY 1, 2
  ORDER BY 1
`));
```

```js
function weeklyChart(width, height = 280) {
  return Plot.plot({
    width,
    height,
    marginLeft: 50,
    color: {legend: true},
    x: {label: null, type: "time"},
    y: {label: "Postings / week", grid: true},
    marks: [
      Plot.lineY(weekly, {x: "wk", y: "n", stroke: "country", curve: "monotone-x"}),
      Plot.dot(weekly, {x: "wk", y: "n", stroke: "country", r: 3, tip: true}),
      Plot.ruleY([0])
    ]
  });
}
```

${weekly.length === 0
  ? html`<div class="card"><div>No postings in current selection.</div></div>`
  : expandable(
      "Weekly postings by country",
      resize((width) => weeklyChart(width)),
      (w, h) => weeklyChart(w, h)
    )}

<small>Week buckets are <code>date_trunc('week', posted_at)</code>; the first and last weeks are usually partial.</small>

## Recent postings

```js
const recent = Array.from(await db.query(`
  SELECT title, company, country, salary_annual_eur_p50, salary_imputed, posted_at, posting_url
  FROM postings
  ${where}
  ORDER BY posted_at DESC NULLS LAST
  LIMIT 100
`));
```

<div class="card">
  ${Inputs.table(recent, {
    columns: ["title", "company", "country", "salary_annual_eur_p50", "salary_imputed", "posted_at"],
    header: {
      title: "Title",
      company: "Company",
      country: "Country",
      salary_annual_eur_p50: "€p50",
      salary_imputed: "Imputed?",
      posted_at: "Posted"
    },
    format: {
      salary_annual_eur_p50: (v) => v == null ? "—" : `€${Math.round(v / 1000)}k`,
      salary_imputed: (v) => v ? "yes" : "",
      posted_at: (v) => fmtDate(v),
      title: (t, i) => recent[i].posting_url
        ? html`<a href="${recent[i].posting_url}" target="_blank" rel="noopener">${t}</a>`
        : t
    },
    width: {country: 70, salary_annual_eur_p50: 80, salary_imputed: 70, posted_at: 100}
  })}
</div>

<small>Up to 100 most-recent postings in the current filter. Click a title to open the original posting.</small>
