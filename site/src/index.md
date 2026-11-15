---
title: Overview
---

# Job Market Analyzer

```js
import * as Plot from "npm:@observablehq/plot";
import {html} from "npm:htl";
import {openDb, loadBootstrap} from "./components/db.js";
import {coverageNote} from "./components/coverageNote.js";
import {dataTable} from "./components/dataTable.js";
import {kpiCard} from "./components/kpiCard.js";
import {marketPulse, derivePulse} from "./components/marketPulse.js";
import {filterCard} from "./components/filterCard.js";
import {expandable} from "./components/expand.js";
import {whereClause, andClause} from "./components/filters.js";

const manifest = await FileAttachment("data/manifest.json").json();
const presets = await FileAttachment("data/presets.json").json();
const db = await openDb();
```

```js
const {countries, iscoPresent, allDates} = await loadBootstrap(db);
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
${manifest.preset_id.replaceAll("_", " ")} preset · weekly snapshot ·
as of <strong>${fmtDate(manifest.generated_at)}</strong> ·
<strong>${(manifest.postings.accumulated_row_count ?? manifest.postings.row_count).toLocaleString()}</strong> postings (${manifest.postings.row_count.toLocaleString()} new this week) ·
<strong>${Object.keys(manifest.postings.country_counts).length}</strong> countries ·
pipeline <code>${manifest.pipeline_version}</code>
</small>

A no-backend, browser-side dashboard. Parquet ships from a GitHub Release; the build turns it into a small SQLite database and charts run in-browser on SQLite (WebAssembly). Filter once at the top — every chart re-flows.

```js
const filters = view(filterCard({countries, iscoPresent, dateBounds: [allDates.lo, allDates.hi], presets}));
```

```js
const where = whereClause(filters);
```

```js
const live = await db.queryRow(`
  SELECT COUNT(*) AS n,
         COUNT(salary_annual_eur_p50) AS n_salary,
         COUNT(isco_code) AS n_isco
  FROM postings ${where}
`);
display(coverageNote(manifest, {n: live.n, nSalary: live.n_salary, nIsco: live.n_isco}));
```

## Market pulse

```js
// Latest *complete* week vs the one before. The week containing the newest
// posting in the snapshot is always partial (weekly Monday ingestion), so it is
// excluded — the cutoff is computed over the whole snapshot, not the filter, so
// the reference week is stable while filters change. Medians on <3 disclosed
// salaries are suppressed as noise.
const pulseWeeks = Array.from(await db.query(`
  SELECT posted_week AS wk,
         COUNT(*) AS n,
         COUNT(salary_annual_eur_p50) AS n_salary,
         median(salary_annual_eur_p50) AS med_salary,
         COUNT(work_arrangement) AS n_arr,
         COUNT(*) FILTER (WHERE work_arrangement = 'remote') AS n_remote
  FROM postings
  ${andClause(where)} posted_at IS NOT NULL
    AND posted_week < (SELECT MAX(posted_week) FROM postings)
  GROUP BY 1
  ORDER BY 1 DESC
  LIMIT 2
`)).map(derivePulse);
const pulse = pulseWeeks[0];
```

${marketPulse(pulse, pulseWeeks[1], {
  periodLabel: pulse ? `wk of ${fmtDate(pulse.wk)}` : "",
  priorLabel: "prior wk",
  emptyText: "No postings in a complete week for the current filter — widen the selection."
})}

<small>Latest <em>complete</em> week (Mon–Sun by <code>posted_at</code>) vs the week before; the newest, still-filling week is excluded. Median salary needs ≥3 disclosed <code>€p50</code>; remote share is among arrangement-classified postings. The <a href="./trends">Trends</a> page shows the same strip plus the full path.</small>

## Key figures

<div class="grid grid-cols-4">
  ${kpiCard("Postings", live.n.toLocaleString(), `of ${(manifest.postings.accumulated_row_count ?? manifest.postings.row_count).toLocaleString()} in snapshot`)}
  ${kpiCard("With salary", live.n ? `${Math.round((live.n_salary / live.n) * 100)}%` : "—", `${live.n_salary.toLocaleString()} disclose €p50`)}
  ${kpiCard("ISCO-tagged", live.n ? `${Math.round((live.n_isco / live.n) * 100)}%` : "—", "rapidfuzz cutoff 85")}
  ${kpiCard("Date span", fmtDate(allDates.lo), `→ ${fmtDate(allDates.hi)}`)}
</div>

## Salary & posting cadence

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

```js
const weekly = Array.from(await db.query(`
  SELECT posted_week AS wk,
         country,
         COUNT(*) AS n
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

<div class="grid grid-cols-2">
  ${salaryRows.length === 0
    ? html`<div class="card"><h2>Annual salary histogram</h2><div>No salary data in current selection.</div></div>`
    : expandable(
        "Annual salary histogram",
        resize((width) => salaryHistogram(width)),
        (w, h) => salaryHistogram(w, h)
      )}
  ${weekly.length === 0
    ? html`<div class="card"><h2>Weekly postings by country</h2><div>No postings in current selection.</div></div>`
    : expandable(
        "Weekly postings by country",
        resize((width) => weeklyChart(width)),
        (w, h) => weeklyChart(w, h)
      )}
</div>

<small>Week buckets are ISO weeks (Monday start, UTC) of <code>posted_at</code>; the first and last weeks are usually partial.</small>

## Recent postings

```js
const recent = Array.from(await db.query(`
  SELECT title, company, country, posted_at,
         salary_annual_eur_p50, salary_imputed, salary_period,
         isco_code, isco_major, isco_match_method, isco_match_score,
         source, work_arrangement, posting_url
  FROM postings
  ${where}
  ORDER BY posted_at DESC NULLS LAST
  LIMIT 2000
`));
```

${dataTable(recent, {
  title: "Recent postings",
  filename: "jobmarket-overview.csv",
  subtitle: "Up to 2,000 most-recent postings in the current filter. Click a title to open the original posting; CSV exports every column.",
  columns: ["title", "company", "country", "salary_annual_eur_p50", "salary_imputed", "posted_at"],
  header: {
    title: "Title",
    company: "Company",
    country: "Country",
    salary_annual_eur_p50: "€p50",
    salary_imputed: "Adzuna estimate?",
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
  width: {country: 70, salary_annual_eur_p50: 80, salary_imputed: 120, posted_at: 100}
})}
